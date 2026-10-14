"""Local bridge server — Chrome extension → KGStore (Neo4j) + VectorStore (ChromaDB)

Run from anywhere:
    python "/path/to/Chrome Plugin/server.py"

Or with a custom port / ChromaDB path:
    PORT=8765 CHROMA_PATH=~/data/chroma python server.py

Add your OpenAI key to a local `.env` file next to this script:
    OPENAI_API_KEY=sk-...

Listens on 127.0.0.1:8765 by default.
"""

import json
import logging
import os
import sys
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

_SERVER_DIR = Path(__file__).resolve().parent
load_dotenv(_SERVER_DIR / ".env")
_LOG_LOCK = threading.Lock()

# ── Path bootstrap — locate local package sources without hardcoded siblings ─
def _normalize_src_dir(path_str: str, package_name: str) -> Optional[Path]:
    path = Path(path_str).expanduser().resolve()
    if (path / package_name).is_dir():
        return path
    if path.name == package_name and path.parent.is_dir():
        return path.parent
    return path if path.is_dir() else None


def _discover_src_dir(env_name: str, package_name: str, relative_candidates: list[str]) -> Optional[Path]:
    explicit = os.getenv(env_name, "").strip()
    if explicit:
        return _normalize_src_dir(explicit, package_name)

    search_roots = [_SERVER_DIR, *_SERVER_DIR.parents]
    for root in search_roots:
        for rel in relative_candidates:
            candidate = _normalize_src_dir(str(root / rel), package_name)
            if candidate:
                return candidate

    return None


_KG_SRC_DIR = _discover_src_dir(
    "KNOWLEDGE_GRAPH_SRC_PATH",
    "knowledge_graph",
    ["knowledge-graph/src", "Database/knowledge-graph/src"],
)
_VECTOR_DB_SRC_DIR = _discover_src_dir(
    "VECTOR_DB_SRC_PATH",
    "vector_db",
    ["vector-db/src", "Database/vector-db/src"],
)

for _src_dir in (_KG_SRC_DIR, _VECTOR_DB_SRC_DIR):
    if _src_dir and str(_src_dir) not in sys.path:
        sys.path.insert(0, str(_src_dir))

_STORE_IMPORT_ERROR = None

try:
    from knowledge_graph.kg_store import KGStore
    from vector_db.vector_store import VectorStore
except ModuleNotFoundError as exc:
    KGStore = None
    VectorStore = None
    _STORE_IMPORT_ERROR = exc

# ── Store instances ───────────────────────────────────────────────────────────
_CHROMA_PATH = Path(os.getenv("CHROMA_PATH", str(_SERVER_DIR / "chroma_data")))
_OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"
_LLM_LOG_PATH = Path(os.getenv("LLM_LOG_PATH", str(_SERVER_DIR / "llm_logs.md"))).expanduser()

kg = KGStore() if KGStore else None
vs = (
    VectorStore(
        chroma_path=_CHROMA_PATH,
        embedding_model=os.getenv("EMBEDDING_MODEL", "nomic-embed-text"),
    )
    if VectorStore else None
)

# ── FastAPI app ───────────────────────────────────────────────────────────────
app = FastAPI(title="Sharpen bridge", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # chrome-extension:// origins require wildcard
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

# ── Request models ────────────────────────────────────────────────────────────
class ConceptIn(BaseModel):
    canonical_name: str
    domain: str = "general"
    summary: str = ""
    aliases: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)

class TripletIn(BaseModel):
    subject: str
    relation: str
    object: str

class FlashcardIn(BaseModel):
    front: str
    back: str

class SourceIn(BaseModel):
    type: str = "youtube"
    video_id: str = ""
    title: str = ""
    url: str = ""
    captured_at: str = ""

class ExtractionIn(BaseModel):
    file_path: str = ""
    concepts: list[ConceptIn] = Field(default_factory=list)
    triplets: list[TripletIn] = Field(default_factory=list)

class IngestPayload(BaseModel):
    schema_version: str = "1.0"
    source: SourceIn
    extraction: ExtractionIn
    flashcards: list[FlashcardIn] = Field(default_factory=list)
    open_question: str = ""


class ChatMessageIn(BaseModel):
    role: str
    content: str


class OpenAIChatIn(BaseModel):
    messages: list[ChatMessageIn] = Field(default_factory=list)
    system_prompt: Optional[str] = None
    max_tokens: int = 1500
    model: str = "gpt-4o-mini"


def _token_param(model: str) -> str:
    return "max_completion_tokens" if model == "gpt-5" or model.startswith("o") else "max_tokens"


def _openai_api_key() -> str:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise HTTPException(
            status_code=500,
            detail="OPENAI_API_KEY is not set. Add it to Chrome Plugin/.env and restart the server.",
        )
    return api_key


def _openai_headers() -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {_openai_api_key()}",
    }


def _build_openai_payload(payload: OpenAIChatIn, *, stream: bool = False) -> dict:
    messages = [m.model_dump() for m in payload.messages]
    if payload.system_prompt:
        messages = [{"role": "system", "content": payload.system_prompt}] + messages

    body = {
        "model": payload.model,
        _token_param(payload.model): payload.max_tokens,
        "messages": messages,
    }

    if stream:
        body["stream"] = True

    return body


def _upstream_error_detail(status_code: int, body: bytes) -> str:
    try:
        data = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return f"OpenAI proxy error {status_code}"

    return data.get("error", {}).get("message") or f"OpenAI proxy error {status_code}"


def _append_llm_log(
    *,
    request_id: str,
    endpoint: str,
    payload: dict,
    response_text: str = "",
    error_text: str = "",
) -> None:
    timestamp = datetime.now(timezone.utc).isoformat()
    _LLM_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    entry_lines = [
        f"## {timestamp} UTC",
        "",
        f"- Request ID: `{request_id}`",
        f"- Endpoint: `{endpoint}`",
        f"- Model: `{payload.get('model', '')}`",
        f"- Stream: `{'true' if payload.get('stream') else 'false'}`",
        f"- Token Param: `{_token_param(payload.get('model', ''))}`",
        "",
        "### Request Payload",
        "",
        "~~~~json",
        json.dumps(payload, ensure_ascii=False, indent=2),
        "~~~~",
        "",
    ]

    if error_text:
        entry_lines.extend([
            "### Error",
            "",
            "~~~~text",
            error_text,
            "~~~~",
            "",
        ])
    else:
        entry_lines.extend([
            "### Response",
            "",
            "~~~~text",
            response_text,
            "~~~~",
            "",
        ])

    entry_lines.append("---")
    entry_lines.append("")

    with _LOG_LOCK:
        with _LLM_LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write("\n".join(entry_lines))


def _ensure_store_modules() -> None:
    if kg and vs:
        return

    detail = "KG + VecDB modules are unavailable in this checkout."
    if _STORE_IMPORT_ERROR:
        detail += f" Missing import: {_STORE_IMPORT_ERROR.name}."

    raise HTTPException(status_code=503, detail=detail)

# ── Endpoints ─────────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {
        "ok": True,
        "kg_loaded": bool(kg),
        "vs_loaded": bool(vs),
        "kg_available": bool(kg and kg.is_available()),
        "vs_available": bool(vs and vs.is_available()),
        "openai_configured": bool(os.getenv("OPENAI_API_KEY", "").strip()),
        "kg_src_path": str(_KG_SRC_DIR) if _KG_SRC_DIR else None,
        "vector_db_src_path": str(_VECTOR_DB_SRC_DIR) if _VECTOR_DB_SRC_DIR else None,
    }


@app.post("/openai/chat")
async def openai_chat(payload: OpenAIChatIn):
    request_id = str(uuid.uuid4())
    upstream_payload = _build_openai_payload(payload)
    async with httpx.AsyncClient(timeout=httpx.Timeout(90.0, connect=10.0)) as client:
        response = await client.post(
            _OPENAI_CHAT_URL,
            headers=_openai_headers(),
            json=upstream_payload,
        )

    if response.status_code >= 400:
        error_detail = _upstream_error_detail(response.status_code, response.content)
        _append_llm_log(
            request_id=request_id,
            endpoint="/openai/chat",
            payload=upstream_payload,
            error_text=error_detail,
        )
        raise HTTPException(
            status_code=502,
            detail=error_detail,
        )

    data = response.json()
    content = data["choices"][0]["message"]["content"]
    _append_llm_log(
        request_id=request_id,
        endpoint="/openai/chat",
        payload=upstream_payload,
        response_text=content,
    )
    return {"content": content}


@app.post("/openai/chat/stream")
async def openai_chat_stream(payload: OpenAIChatIn):
    request_id = str(uuid.uuid4())
    upstream_payload = _build_openai_payload(payload, stream=True)
    client = httpx.AsyncClient(timeout=httpx.Timeout(connect=10.0, read=None, write=90.0, pool=90.0))
    request = client.build_request(
        "POST",
        _OPENAI_CHAT_URL,
        headers=_openai_headers(),
        json=upstream_payload,
    )
    response = await client.send(request, stream=True)

    if response.status_code >= 400:
        body = await response.aread()
        await response.aclose()
        await client.aclose()
        error_detail = _upstream_error_detail(response.status_code, body)
        _append_llm_log(
            request_id=request_id,
            endpoint="/openai/chat/stream",
            payload=upstream_payload,
            error_text=error_detail,
        )
        raise HTTPException(
            status_code=502,
            detail=error_detail,
        )

    async def iter_text():
        chunks: list[str] = []
        try:
            async for line in response.aiter_lines():
                if not line or not line.startswith("data: "):
                    continue

                payload_text = line[6:].strip()
                if not payload_text or payload_text == "[DONE]":
                    continue

                try:
                    delta = json.loads(payload_text).get("choices", [{}])[0].get("delta", {}).get("content", "")
                except json.JSONDecodeError:
                    continue

                if delta:
                    chunks.append(delta)
                    yield delta
        finally:
            _append_llm_log(
                request_id=request_id,
                endpoint="/openai/chat/stream",
                payload=upstream_payload,
                response_text="".join(chunks),
            )
            await response.aclose()
            await client.aclose()

    return StreamingResponse(iter_text(), media_type="text/plain; charset=utf-8")


@app.post("/ingest")
def ingest(payload: IngestPayload):
    _ensure_store_modules()
    source_label = payload.source.url or payload.source.title

    # ── 1. Concepts → KG nodes ────────────────────────────────────────────────
    name_to_id: dict[str, str] = {}
    nodes_written = 0

    for c in payload.extraction.concepts:
        node = KGStore.make_node(c.canonical_name, c.domain)
        name_to_id[c.canonical_name.lower()] = node.id
        kg.upsert_node(node)
        nodes_written += 1

    # ── 2. Triplets → KG edges ────────────────────────────────────────────────
    edges = []
    for t in payload.extraction.triplets:
        subj_id = name_to_id.get(t.subject.lower())
        obj_id  = name_to_id.get(t.object.lower())

        if not subj_id:
            stub = KGStore.make_node(t.subject, "general")
            kg.upsert_node(stub)
            name_to_id[t.subject.lower()] = stub.id
            subj_id = stub.id

        if not obj_id:
            stub = KGStore.make_node(t.object, "general")
            kg.upsert_node(stub)
            name_to_id[t.object.lower()] = stub.id
            obj_id = stub.id

        edges.append(KGStore.make_edge(subj_id, t.relation, obj_id, source=source_label))

    if edges:
        kg.upsert_edge_batch(edges)

    # ── 3. Concept summaries → VectorStore ───────────────────────────────────
    vs_ids, vs_texts, vs_metas = [], [], []

    for c in payload.extraction.concepts:
        node_id = name_to_id.get(c.canonical_name.lower())
        if node_id and c.summary:
            vs_ids.append(node_id)
            vs_texts.append(c.summary)
            vs_metas.append({
                "canonical_name": c.canonical_name,
                "domain": c.domain,
                "tags": ",".join(c.tags),
                "source_type": payload.source.type,
                "title": payload.source.title,
                "url": payload.source.url,
            })

    if vs_ids:
        vs.upsert_batch("concepts", vs_ids, vs_texts, vs_metas)

    # ── 4. Flashcards → VectorStore ───────────────────────────────────────────
    fc_ids, fc_texts, fc_metas = [], [], []

    for fc in payload.flashcards:
        fc_ids.append(str(uuid.uuid4()))
        fc_texts.append(f"{fc.front} | {fc.back}")
        fc_metas.append({
            "front": fc.front,
            "back": fc.back,
            "source_type": payload.source.type,
            "title": payload.source.title,
            "url": payload.source.url,
        })

    if fc_ids:
        vs.upsert_batch("flashcards", fc_ids, fc_texts, fc_metas)

    return {
        "ok": True,
        "nodes_upserted": nodes_written,
        "edges_upserted": len(edges),
        "concepts_vectorised": len(vs_ids),
        "flashcards_vectorised": len(fc_ids),
    }


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8765"))
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logging.info("Starting Sharpen bridge on http://127.0.0.1:%d", port)
    logging.info("OpenAI key: %s", "loaded from .env" if os.getenv("OPENAI_API_KEY", "").strip() else "missing")
    logging.info("LLM log file: %s", _LLM_LOG_PATH)
    logging.info("knowledge-graph src: %s", _KG_SRC_DIR or "not found")
    logging.info("vector-db src: %s", _VECTOR_DB_SRC_DIR or "not found")
    if kg:
        logging.info("KG (Neo4j): %s", "available" if kg.is_available() else "not connected")
    else:
        logging.warning("KG modules unavailable: %s", _STORE_IMPORT_ERROR)
    logging.info("VecDB (ChromaDB) path: %s", _CHROMA_PATH)
    uvicorn.run(app, host="127.0.0.1", port=port)
