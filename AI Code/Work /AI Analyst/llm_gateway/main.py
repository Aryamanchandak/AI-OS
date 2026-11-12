import logging
import os, time, json
from pathlib import Path
from typing import Optional
from contextlib import asynccontextmanager

log = logging.getLogger(__name__)

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from jsonschema import Draft202012Validator, ValidationError

ROOT = Path(__file__).parent
load_dotenv(ROOT.parent / ".env")

import db
import providers as P
from router import Router, LIMITS, SHORTCUTS, resolve
from cache import GeminiCache
from schemas import ChatRequest, ChatResponse, ToolCall, EmbedRequest, EmbedResponse
import embedders as E

# Default failover order: cheap local first, then cheapest Gemini, flash, pro.
DEFAULT_ORDER = ["gemma", "gemini-cheap", "gemini-flash", "gemini-pro"]
ORDER = [x.strip() for x in os.getenv("LLM_ORDER", ",".join(DEFAULT_ORDER)).split(",") if x.strip()]
PORT = int(os.getenv("GATEWAY_V7_PORT", "8107"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init()
    app.state.cache = GeminiCache(ttl_seconds=300)
    app.state.providers = P.build_providers(app.state.cache)
    app.state.router = Router(app.state.providers, ORDER)
    app.state.embedders, app.state.embed_order = E.build_embedders()
    log.info("gateway started — providers=%s order=%s embedders=%s",
             list(app.state.router.providers), app.state.router.order,
             app.state.embed_order)
    if not app.state.router.order:
        log.error(
            "router.order is EMPTY — LLM_ORDER=%r names don't match any built provider. "
            "Valid names: %s", os.getenv("LLM_ORDER"), list(app.state.router.providers)
        )
    yield


app = FastAPI(title="LLM Gateway V7", lifespan=lifespan)


def _normalize_messages(req: ChatRequest):
    if req.messages:
        return list(req.messages)
    return [{"role": "user", "content": req.prompt or ""}]


def _system_blocks(req: ChatRequest):
    if req.system is None:
        return None
    if isinstance(req.system, str):
        if req.cache_system:
            return [{"text": req.system, "cache": True}]
        return req.system
    return [b.model_dump() if hasattr(b, "model_dump") else b for b in req.system]


def _est_tokens(messages, system_blocks, max_tokens):
    chars = sum(len(str(m.get("content", ""))) for m in messages)
    if isinstance(system_blocks, str):
        chars += len(system_blocks)
    elif isinstance(system_blocks, list):
        for b in system_blocks:
            chars += len(b.get("text", "") if isinstance(b, dict) else "")
    return chars // 4 + max_tokens


def _backoff_for(err: Exception, has_model_override: bool = False):
    msg = str(err).lower()
    status = getattr(err, "status", None)
    if status == 429:
        if "queue" in msg: return 15, "server queue full"
        if "quota" in msg or "rpm" in msg or "per minute" in msg: return 60, "RPM quota burned"
        if "rpd" in msg or "per day" in msg or "daily" in msg: return 3600, "RPD quota burned"
        return 30, "rate limited"
    if status and 500 <= status < 600: return 20, f"upstream {status}"
    if status == 408 or "timeout" in msg: return 10, "timeout"
    if status in (401, 403):
        if has_model_override:
            return 0, ""
        return 600, "auth error"
    if status == 404 and has_model_override:
        return 0, ""
    return 0, ""


def _attempts_str(attempts):
    return "; ".join(f"{a['provider']}:{a['reason']}" for a in attempts)


def _required_caps(req: ChatRequest):
    caps = []
    if req.tools: caps.append("tools")
    if req.reasoning and req.reasoning != "off": caps.append("reasoning")
    if req.response_format: caps.append("structured")
    return caps


def _validate_structured(text: str, schema: dict):
    try:
        obj = json.loads(text)
    except Exception as e:
        raise ValueError(f"output is not JSON: {e}")
    Draft202012Validator(schema).validate(obj)
    return obj


@app.post("/v1/chat")
async def chat(req: ChatRequest):
    router = app.state.router
    messages = _normalize_messages(req)
    system_blocks = _system_blocks(req)
    prompt_text = "".join(str(m.get("content", "")) for m in messages)
    est = _est_tokens(messages, system_blocks, req.max_tokens)
    explicit_override = bool(req.provider)
    required_caps = _required_caps(req)

    candidates = router.candidates(req.provider) if req.provider else list(router.order)

    if req.provider and not candidates:
        raise HTTPException(400, f"unknown provider '{req.provider}'. Known: {list(router.providers)} or shortcuts {list(SHORTCUTS)}")

    all_attempts = []
    last_err = None

    if explicit_override and len(candidates) == 1:
        import asyncio as _asyncio
        deadline = time.time() + 30
        while time.time() < deadline:
            name, _ = router.pick(est, candidates, required_caps=required_caps)
            if name is not None:
                break
            cd = router.state[candidates[0]].snapshot(LIMITS[candidates[0]])["cooldown_remaining"]
            if cd <= 0 or cd > 30:
                break
            await _asyncio.sleep(min(cd + 0.05, 5))

    for _ in range(len(candidates) + 1):
        name, atts = router.pick(est, candidates, required_caps=required_caps)
        all_attempts.extend(atts)
        if name is None:
            break

        provider = router.providers[name]
        t0 = time.time()
        router.state[name].record(0)

        try:
            if req.stream:
                async def gen():
                    try:
                        agg = []
                        has_tool_call = False
                        async for chunk in provider.stream(messages,
                                                          max_tokens=req.max_tokens,
                                                          temperature=req.temperature,
                                                          model=req.model,
                                                          tools=req.tools,
                                                          tool_choice=req.tool_choice,
                                                          reasoning=req.reasoning,
                                                          response_format=req.response_format,
                                                          system_blocks=system_blocks,
                                                          cache_system=bool(req.cache_system)):
                            agg.append(chunk)
                            if chunk.startswith("[[TOOL_CALL_DELTA]]"):
                                has_tool_call = True
                                yield f"data: {json.dumps({'provider': name, 'tool_call_delta': chunk[len('[[TOOL_CALL_DELTA]] '):]})}\n\n"
                            else:
                                yield f"data: {json.dumps({'provider': name, 'delta': chunk})}\n\n"
                        text = "".join(agg)
                        latency = int((time.time() - t0) * 1000)

                        parsed = None
                        if req.response_format and req.response_format.schema_ and not has_tool_call:
                            try:
                                parsed = _validate_structured(text, req.response_format.schema_)
                            except (ValueError, ValidationError) as ve:
                                fix_msgs = list(messages) + [
                                    {"role": "assistant", "content": text},
                                    {"role": "user", "content": f"Your previous reply did not match the required JSON schema: {ve}. Reply ONLY with valid JSON conforming to the schema."},
                                ]
                                try:
                                    fix_result = await provider.chat(fix_msgs,
                                                                     max_tokens=req.max_tokens,
                                                                     temperature=0,
                                                                     model=req.model,
                                                                     response_format=req.response_format,
                                                                     system_blocks=system_blocks,
                                                                     cache_system=bool(req.cache_system))
                                    parsed = _validate_structured(fix_result["text"], req.response_format.schema_)
                                    text = fix_result["text"]
                                    tokens = (fix_result["input_tokens"] or 0) + (fix_result["output_tokens"] or 0)
                                    router.state[name].tokens_today += tokens
                                    router.state[name].tokens_minute.append((time.time(), tokens))
                                except (ValueError, ValidationError) as ve2:
                                    db.log_call(provider=name, model=req.model or provider.model,
                                                status="error", error=f"stream_structured_fix_failed: {str(ve2)[:200]}",
                                                latency_ms=int((time.time() - t0) * 1000),
                                                prompt_chars=len(prompt_text),
                                                override=req.provider, attempted=_attempts_str(all_attempts))
                                    yield f"data: {json.dumps({'error': f'structured output failed validation: {str(ve2)[:200]}'})}\n\n"
                                    return
                                except Exception as fe:
                                    db.log_call(provider=name, model=req.model or provider.model,
                                                status="error", error=f"stream_fix_up_failed: {str(fe)[:200]}",
                                                latency_ms=int((time.time() - t0) * 1000),
                                                prompt_chars=len(prompt_text),
                                                override=req.provider, attempted=_attempts_str(all_attempts))
                                    yield f"data: {json.dumps({'error': f'fix-up call failed: {str(fe)[:200]}'})}\n\n"
                                    return

                        db.log_call(provider=name, model=req.model or provider.model,
                                    latency_ms=latency, status="ok",
                                    prompt_chars=len(prompt_text), response_chars=len(text),
                                    override=req.provider, attempted=_attempts_str(all_attempts))
                        done_payload: dict = {"done": True, "provider": name}
                        if parsed is not None:
                            done_payload["parsed"] = parsed
                            done_payload["text"] = text
                        yield f"data: {json.dumps(done_payload)}\n\n"
                    except Exception as e:
                        db.log_call(provider=name, model=req.model or provider.model,
                                    status="error", error=str(e)[:500],
                                    latency_ms=int((time.time() - t0) * 1000),
                                    prompt_chars=len(prompt_text),
                                    override=req.provider, attempted=_attempts_str(all_attempts))
                        yield f"data: {json.dumps({'error': str(e)[:300]})}\n\n"
                return StreamingResponse(gen(), media_type="text/event-stream")

            result = await provider.chat(messages,
                                         max_tokens=req.max_tokens,
                                         temperature=req.temperature,
                                         model=req.model,
                                         tools=req.tools,
                                         tool_choice=req.tool_choice,
                                         reasoning=req.reasoning,
                                         response_format=req.response_format,
                                         system_blocks=system_blocks,
                                         cache_system=bool(req.cache_system))
            latency = int((time.time() - t0) * 1000)

            parsed = None
            if req.response_format and req.response_format.schema_ and not result["tool_calls"]:
                try:
                    parsed = _validate_structured(result["text"], req.response_format.schema_)
                except (ValueError, ValidationError) as ve:
                    fix_msgs = list(messages) + [
                        {"role": "assistant", "content": result["text"]},
                        {"role": "user", "content": f"Your previous reply did not match the required JSON schema: {ve}. Reply ONLY with valid JSON conforming to the schema."},
                    ]
                    result = await provider.chat(fix_msgs,
                                                 max_tokens=req.max_tokens,
                                                 temperature=0,
                                                 model=req.model,
                                                 response_format=req.response_format,
                                                 system_blocks=system_blocks,
                                                 cache_system=bool(req.cache_system))
                    try:
                        parsed = _validate_structured(result["text"], req.response_format.schema_)
                    except (ValueError, ValidationError) as ve2:
                        raise HTTPException(503, f"structured output failed validation: {ve2}")

            tokens = (result["input_tokens"] or 0) + (result["output_tokens"] or 0)
            router.state[name].tokens_today += tokens
            router.state[name].tokens_minute.append((time.time(), tokens))
            db.log_call(provider=name, model=result["model"],
                        input_tokens=result["input_tokens"], output_tokens=result["output_tokens"],
                        cache_create_tokens=result["cache_creation_input_tokens"],
                        cache_read_tokens=result["cache_read_input_tokens"],
                        latency_ms=latency, status="ok",
                        prompt_chars=len(prompt_text), response_chars=len(result["text"]),
                        override=req.provider, attempted=_attempts_str(all_attempts),
                        tool_calls=len(result["tool_calls"]),
                        reasoning_applied=result["reasoning_applied"],
                        tool_dialect=result["tool_call_dialect"],
                        call_role="worker")
            return ChatResponse(
                provider=name,
                model=result["model"],
                text=result["text"],
                tool_calls=[ToolCall(**tc) for tc in result["tool_calls"]],
                stop_reason=result["stop_reason"],
                input_tokens=result["input_tokens"],
                output_tokens=result["output_tokens"],
                cache_creation_input_tokens=result["cache_creation_input_tokens"],
                cache_read_input_tokens=result["cache_read_input_tokens"],
                latency_ms=latency,
                tool_call_dialect=result["tool_call_dialect"],
                reasoning_applied=result["reasoning_applied"],
                parsed=parsed,
                attempted=all_attempts,
            ).model_dump()

        except P.ProviderError as e:
            last_err = str(e)
            secs, reason = _backoff_for(e, has_model_override=bool(req.model))
            if secs > 0:
                router.state[name].mark_unavailable(secs, reason)
            db.log_call(provider=name, model=req.model or provider.model,
                        status="error", error=str(e)[:500],
                        latency_ms=int((time.time() - t0) * 1000),
                        prompt_chars=len(prompt_text),
                        override=req.provider, attempted=_attempts_str(all_attempts))
            tag = f"failed: {str(e)[:100]}"
            if secs > 0: tag += f" → backoff {secs:.0f}s ({reason})"
            all_attempts.append({"provider": name, "reason": tag})
            if explicit_override or not getattr(e, "retryable", True):
                raise HTTPException(502, f"{name} failed: {e}")
            candidates = [c for c in candidates if c != name]
            continue
        except HTTPException:
            raise
        except Exception as e:
            last_err = str(e)
            secs, reason = _backoff_for(e, has_model_override=bool(req.model))
            if secs > 0:
                router.state[name].mark_unavailable(secs, reason)
            db.log_call(provider=name, model=req.model or provider.model,
                        status="error", error=str(e)[:500],
                        latency_ms=int((time.time() - t0) * 1000),
                        prompt_chars=len(prompt_text),
                        override=req.provider, attempted=_attempts_str(all_attempts))
            all_attempts.append({"provider": name, "reason": f"exception: {str(e)[:120]}"})
            if explicit_override:
                raise HTTPException(502, f"{name} failed: {e}")
            candidates = [c for c in candidates if c != name]
            continue

    log.error("all providers unavailable — attempts=%s last_error=%s", all_attempts, last_err)
    raise HTTPException(503, f"all providers unavailable. attempts: {all_attempts}. last_error: {last_err}")


@app.post("/v1/embed")
async def embed(req: EmbedRequest):
    """Embed text. Failover: Ollama (nomic-embed-text) → Gemini embedding."""
    embedders = app.state.embedders
    if not embedders:
        raise HTTPException(503, "no embedding providers configured")

    if len(req.text) > E.MAX_INPUT_CHARS:
        raise HTTPException(
            413,
            f"text is {len(req.text)} chars; embed input is capped at "
            f"{E.MAX_INPUT_CHARS} chars. Chunk the input and embed each chunk.",
        )

    t0 = time.time()
    try:
        name, result, attempts, latency = await E.embed_with_failover(
            embedders, req.text, req.task_type, explicit=req.provider
        )
    except E.EmbedderError as e:
        latency = int((time.time() - t0) * 1000)
        db.log_call(
            provider=req.provider or "(any)",
            model="(none)",
            status="error",
            error=str(e)[:500],
            latency_ms=latency,
            prompt_chars=len(req.text),
            override=req.provider,
            call_role="embed",
        )
        if req.provider:
            if e.status == 429:
                raise HTTPException(429, f"{req.provider} rate-limited: {e}")
            if e.status == 400:
                raise HTTPException(400, str(e))
            raise HTTPException(502, f"{req.provider} embed failed: {e}")
        raise HTTPException(503, str(e))

    db.log_call(
        provider=name,
        model=result["model"],
        status="ok",
        latency_ms=latency,
        prompt_chars=len(req.text),
        override=req.provider,
        attempted=_attempts_str(attempts),
        call_role="embed",
        embed_dim=result["dim"],
    )
    return EmbedResponse(
        provider=name,
        model=result["model"],
        embedding=result["embedding"],
        dim=result["dim"],
        latency_ms=latency,
        attempted=attempts,
    ).model_dump()


@app.get("/v1/embedders")
async def list_embedders():
    return {
        "order": app.state.embed_order,
        "models": {e.name: e.model for e in app.state.embedders},
        "fixed_dim": E.EMBED_DIM,
        "max_input_chars": E.MAX_INPUT_CHARS,
        "backoff_steps_s": E.BACKOFF_STEPS,
        "live": {e.name: e.state.snapshot() for e in app.state.embedders},
        "today": db.aggregate(call_role="embed"),
    }


@app.get("/v1/providers")
async def list_providers():
    r = app.state.router
    return {
        "order": r.order,
        "providers": list(r.providers.keys()),
        "shortcuts": SHORTCUTS,
        "limits": LIMITS,
        "models": {n: p.model for n, p in r.providers.items()},
    }


@app.get("/v1/capabilities")
async def capabilities():
    r = app.state.router
    out = {}
    for name, p in r.providers.items():
        caps = dict(getattr(p, "capabilities", {}))
        caps = P.model_capabilities(name, p.model, caps)
        caps["model"] = p.model
        caps.update({
            "max_ctx": LIMITS[name]["max_ctx"],
            "rpm": LIMITS[name]["rpm"],
            "rpd": LIMITS[name]["rpd"],
        })
        out[name] = caps
    return out


@app.get("/v1/status")
async def status():
    r = app.state.router
    return {"order": r.order, "live": r.all_status(),
            "today": db.aggregate(call_role="worker"), "limits": LIMITS}


@app.get("/v1/calls")
async def calls(limit: int = 100, provider: Optional[str] = None, status: Optional[str] = None):
    return db.recent(limit=limit, provider=provider, status=status)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=False)
