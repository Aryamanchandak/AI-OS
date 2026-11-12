#!/usr/bin/env python3
"""Per-provider smoke test for llm_gatewayV7.

Tests basic text, tool calling, and structured output for the currently
configured providers. Providers are included only when their API keys are
present in the environment.
"""
from __future__ import annotations

import json
import os
import sys
import time

import httpx

URL = os.getenv("LLM_GATEWAY_V7_URL", "http://localhost:8107")

PROVIDERS = []
if os.getenv("OLLAMA_URL"):
    PROVIDERS.append("gemma")
if os.getenv("GEMINI_API_KEY"):
    PROVIDERS.extend(["gemini-cheap", "gemini-flash", "gemini-pro"])
if os.getenv("OPENAI_API_KEY"):
    PROVIDERS.extend(["openai-cheap", "openai-mini", "openai-pro"])
if os.getenv("ANTHROPIC_API_KEY"):
    PROVIDERS.extend(["anthropic-haiku", "anthropic-sonnet", "anthropic-opus"])

ADD_TOOL = {
    "name": "add",
    "description": "Return a + b.",
    "input_schema": {
        "type": "object",
        "properties": {"a": {"type": "number"}, "b": {"type": "number"}},
        "required": ["a", "b"],
    },
}

CITY_SCHEMA = {
    "type": "object",
    "properties": {"city": {"type": "string"}, "country": {"type": "string"}},
    "required": ["city", "country"],
}


def post(body, timeout=120):
    r = httpx.post(f"{URL}/v1/chat", json=body, timeout=timeout)
    try:
        payload = r.json()
    except Exception:
        payload = {"raw": r.text}
    return r.status_code, payload


def test_basic(provider: str):
    code, d = post({"prompt": "Say hi in 3 words.", "provider": provider, "max_tokens": 256})
    if code == 200 and d.get("text", "").strip():
        return "OK", d["text"].strip()[:40]
    return "FAIL", f"code={code} {str(d)[:120]}"


def test_tools(provider: str):
    msgs = [{"role": "user", "content": "What is 7 plus 5? Use the add tool."}]
    code, d = post({
        "messages": msgs,
        "provider": provider,
        "tools": [ADD_TOOL],
        "tool_choice": "auto",
        "temperature": 0,
        "max_tokens": 512,
    }, timeout=180)
    if code != 200:
        return "FAIL", f"first call code={code} {str(d)[:120]}"
    tcs = d.get("tool_calls") or []
    if not tcs:
        return "FAIL", f"no tool_calls; text={d.get('text', '')[:80]}"
    tc = tcs[0]
    args = tc.get("arguments") or {}
    if {args.get("a"), args.get("b")} not in ({7, 5}, {7.0, 5.0}):
        return "PARTIAL", f"tool_call args={args}"
    msgs2 = msgs + [
        {"role": "assistant", "content": "", "tool_calls": [tc]},
        {"role": "tool", "tool_call_id": tc["id"], "tool_name": tc["name"], "content": json.dumps({"result": 12})},
    ]
    code, d2 = post({
        "messages": msgs2,
        "provider": provider,
        "tools": [ADD_TOOL],
        "temperature": 0,
        "max_tokens": 256,
    }, timeout=180)
    if code != 200:
        return "PARTIAL", f"second call code={code} {str(d2)[:120]}"
    final = (d2.get("text") or "").strip()
    if "12" in final:
        return "OK", final[:40]
    return "PARTIAL", f"final={final[:60]!r}"


def test_structured(provider: str):
    code, d = post({
        "prompt": "Paris is in which country? Respond with JSON {city,country}.",
        "provider": provider,
        "temperature": 0,
        "max_tokens": 512,
        "response_format": {"type": "json_schema", "schema": CITY_SCHEMA, "name": "loc", "strict": True},
    })
    if code != 200:
        return "FAIL", f"code={code} {str(d)[:120]}"
    parsed = d.get("parsed")
    if parsed and parsed.get("city", "").lower() == "paris" and parsed.get("country", "").lower() == "france":
        return "OK", str(parsed)
    return "PARTIAL", f"parsed={parsed} text={(d.get('text') or '')[:80]!r}"


def run_provider(provider: str):
    row = {}
    details = {}
    for col, fn in [("basic", test_basic), ("tools", test_tools), ("struct", test_structured)]:
        try:
            status, info = fn(provider)
        except Exception as e:
            status, info = "FAIL", f"exc {e}"
        row[col] = status
        details[col] = info
        print(f"  [{provider:18s}] {col:8s} → {status:7s} {info[:100]}", flush=True)
    return provider, row, details


def main():
    if not PROVIDERS:
        print("No configured providers found in env; nothing to test.")
        return
    import concurrent.futures as cf

    matrix = {}
    print("Running V7 providers in parallel...\n", flush=True)
    with cf.ThreadPoolExecutor(max_workers=len(PROVIDERS)) as ex:
        futs = {ex.submit(run_provider, p): p for p in PROVIDERS}
        for fut in cf.as_completed(futs):
            name, row, _ = fut.result()
            matrix[name] = row

    print("\n" + "=" * 78)
    cols = ["basic", "tools", "struct"]
    print(f"{'provider':20s}" + "  ".join(f"{c:9s}" for c in cols))
    print("-" * 78)
    for name in PROVIDERS:
        row = matrix.get(name, {})
        print(f"{name:20s}" + "  ".join(f"{row.get(c, '?'):9s}" for c in cols))
    print("=" * 78)

    bad = [name for name, row in matrix.items() if row.get("basic") == "FAIL"]
    if bad:
        print(f"\nFAIL: basic test broken on: {bad}")
        sys.exit(1)
    print("\nBasic smoke test passed.")


if __name__ == "__main__":
    main()
