"""index_transcript.py — Transcribe a podcast and forward it into the 3 AI-OS stores.

Thin glue, by design. It does NOT implement any new ingestion mechanism — it just
imports the existing functions of each store and forwards the transcript data:

    1. transcript  : ingestion.ingest.fetch_audio + transcription.transcribe.transcribe
    2. memory       : write a markdown file into "Persistent Memory Chats Storage/Podcast Transcripts/"
    3. vector DB    : wrap chunks as AtomicFact -> VectorStore.embed_and_store_atomic_fact
    4. knowledge KG : extract concepts/triplets -> SqliteStore.upsert_concept + KGStore.upsert_edge

Run:
    .venv/bin/python scripts/index_transcript.py "<podcast-url>"

A future unified ingestion layer can import the helper functions below directly.
"""

from __future__ import annotations

import json
import re
import sys
import uuid
from datetime import date, datetime
from pathlib import Path

# ── sys.path wiring ───────────────────────────────────────────────────────────
# The project path contains spaces ("AI OS/projects/Podcast to Text /"), which
# breaks pip editable-install .pth resolution (see memory `env-setup`). We sidestep
# that by adding each package's src/ dir to sys.path directly — manual insertion is
# unaffected by the spaced-path bug.
PROJECT_ROOT = Path(__file__).resolve().parent.parent          # .../podcast-brief
AI_OS_PROJECTS = PROJECT_ROOT.parent.parent                    # .../projects
for p in (
    PROJECT_ROOT,                                              # ingestion/, transcription/, core/
    AI_OS_PROJECTS / "study-system" / "src",
    AI_OS_PROJECTS / "knowledge-graph" / "src",
    AI_OS_PROJECTS / "vector-db" / "src",
):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)

MIGRATIONS_DIR = AI_OS_PROJECTS / "study-system" / "src" / "study_system" / "storage" / "migrations"
MEMORY_DIR = AI_OS_PROJECTS / "Persistent Memory Chats Storage" / "Podcast Transcripts"
DATA_DIR = PROJECT_ROOT / "data"
CHROMA_PATH = DATA_DIR / "chroma"
KG_DB_PATH = DATA_DIR / "kg" / "study_system.db"
DOMAIN = "podcast"
EXTRACTION_MODEL = "claude-opus-4-8"

# Load .env so DEEPGRAM_API_KEY / ANTHROPIC_API_KEY are available for our own calls
try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except Exception:
    pass

# ── existing project + store imports (after sys.path wiring) ──────────────────
from ingestion import ingest                                   # noqa: E402
from transcription import transcribe                           # noqa: E402
from transcription.transcribe import Transcript                # noqa: E402

from study_system.types.extraction import (                   # noqa: E402
    AtomicFact, Concept, FactType, RelationType, SourceAnchor, Triplet,
)
from study_system.storage.sqlite_store import SqliteStore      # noqa: E402
from knowledge_graph.kg_store import KGStore, CycleDetected    # noqa: E402
from vector_db.vector_store import VectorStore                 # noqa: E402


# ── small helpers ─────────────────────────────────────────────────────────────

def _slug(text: str, max_len: int = 60) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return s[:max_len] or "untitled"


def chunk_segments(tr: Transcript, segments_per_chunk: int = 6) -> list[dict]:
    """Group consecutive transcript segments into simple chunks (dead-simple, no subsystem)."""
    chunks: list[dict] = []
    segs = tr.segments
    for i in range(0, len(segs), segments_per_chunk):
        group = segs[i : i + segments_per_chunk]
        if not group:
            continue
        text = " ".join(f"[{s.speaker}] {s.text}" for s in group).strip()
        if not text:
            continue
        chunks.append({
            "text": text,
            "speaker": group[0].speaker,
            "start": group[0].start,
            "end": group[-1].end,
        })
    return chunks


# ── stage 1: transcript ───────────────────────────────────────────────────────

def make_transcript(url: str) -> tuple[Transcript, "ingest.EpisodeInfo"]:
    print(f"→ Fetching audio: {url}")
    info = ingest.fetch_audio(url)
    print(f"  episode_id={info.id}  title={info.title}")
    print("→ Transcribing (Deepgram Nova-3)…")
    tr = transcribe.transcribe(info.audio_path, info.id)
    print(f"  {len(tr.segments)} segments, {len(tr.speakers)} speakers, "
          f"{tr.duration_seconds/60:.1f} min")
    return tr, info


# ── stage 2: memory archive ───────────────────────────────────────────────────

def forward_to_memory(tr: Transcript, info) -> Path:
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    fname = f"{date.today().isoformat()}_{info.id}_{_slug(info.title)}.md"
    path = MEMORY_DIR / fname
    header = (
        f"# {info.title}\n\n"
        f"- **Source URL:** {info.source_url}\n"
        f"- **Episode ID:** {info.id}\n"
        f"- **Speakers:** {', '.join(tr.speakers)}\n"
        f"- **Duration:** {tr.duration_seconds/60:.1f} min\n"
        f"- **Archived:** {datetime.now().isoformat(timespec='seconds')}\n\n"
        f"---\n\n"
    )
    path.write_text(header + tr.to_prompt_format())
    print(f"  ✓ memory archive: {path}")
    return path


# ── stage 3: vector DB ────────────────────────────────────────────────────────

def _warm_embedding_cache() -> None:
    """Force the default ONNX MiniLM model to download/load synchronously.

    With no OpenAI key VectorStore uses ChromaDB's default embedder, which lazily
    downloads an ~80MB model on first embed. That download races the embed call and
    VectorStore swallows the exception, so the first run can silently store nothing
    (see memory `kgvec-venv`). Warming the cache here makes the real writes reliable.
    """
    try:
        from chromadb.utils.embedding_functions import DefaultEmbeddingFunction
        DefaultEmbeddingFunction()(["warmup"])
    except Exception as e:
        print(f"  ⚠ embedding warm-up failed (continuing): {e}")


def forward_to_vector(tr: Transcript, info, transcript_file: str, extraction_id: str) -> int:
    vs = VectorStore(chroma_path=CHROMA_PATH, openai_api_key=None)  # local default embeddings
    if not vs.is_available():
        print("  ⚠ ChromaDB unavailable — skipping vector DB.")
        return 0
    _warm_embedding_cache()
    chunks = chunk_segments(tr)
    n = 0
    for ch in chunks:
        fact = AtomicFact(
            id=str(uuid.uuid4()),
            claim=ch["text"],
            concept_canonical_name=info.title,
            source_anchor=SourceAnchor(
                file=transcript_file,
                highlight_id=f"seg_{int(ch['start'])}",
                char_range=(0, len(ch["text"])),
                highlight_text=ch["text"][:500],
            ),
            fact_type=FactType.other,
            extraction_id=extraction_id,
        )
        vs.embed_and_store_atomic_fact(fact)  # existing ingest call
        n += 1
    # Confirm the writes actually landed (write methods swallow exceptions silently)
    try:
        import chromadb
        col = chromadb.PersistentClient(path=str(CHROMA_PATH)).get_or_create_collection("atomic_facts")
        print(f"  ✓ vector DB: forwarded {n} chunks (atomic_facts count={col.count()})")
    except Exception:
        print(f"  ✓ vector DB: forwarded {n} chunks")
    return n


# ── stage 4: knowledge graph ──────────────────────────────────────────────────

def apply_migrations(conn) -> None:
    """Apply unapplied SQL migrations in order (reuses study_system's migration files)."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations "
        "(version TEXT PRIMARY KEY, applied_at TIMESTAMP NOT NULL)"
    )
    conn.commit()
    applied = {r[0] for r in conn.execute("SELECT version FROM schema_migrations")}
    for mf in sorted(MIGRATIONS_DIR.glob("*.sql")):
        version = mf.stem.split("_")[0]
        if version in applied:
            continue
        conn.executescript(mf.read_text())
        conn.execute(
            "INSERT OR IGNORE INTO schema_migrations (version, applied_at) VALUES (?, ?)",
            (version, datetime.utcnow().isoformat()),
        )
        conn.commit()


def extract_concepts_triplets(tr: Transcript, info, extraction_id: str) -> tuple[list[Concept], list[Triplet]]:
    """One Claude call → concepts + subject/relation/object triplets in the existing types."""
    import os
    import anthropic

    relations = [r.value for r in RelationType]
    prompt = f"""You are building a knowledge graph from a podcast transcript.

Episode: "{info.title}"

From the transcript below, extract:
1. The key CONCEPTS discussed (people, ideas, technologies, organizations, theories).
2. TRIPLETS describing relationships between those concepts, as subject / relation / object.

Allowed relation types (use the closest fit; default to RELATES_TO when unsure):
{", ".join(relations)}

Rules:
- Use concise, canonical concept names (a few words, Title Case where natural).
- Every subject and object in a triplet MUST also appear in the concepts list.
- Aim for the ~15-30 most important concepts and ~20-40 triplets. Quality over quantity.
- Return ONLY valid JSON, no preamble, in exactly this shape:
{{"concepts": [{{"canonical_name": "...", "summary": "one sentence"}}],
  "triplets": [{{"subject": "...", "relation": "RELATES_TO", "object": "..."}}]}}

TRANSCRIPT:
{tr.to_prompt_format()}
"""
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    resp = client.messages.create(
        model=EXTRACTION_MODEL,
        max_tokens=8000,
        messages=[{"role": "user", "content": prompt}],
    )
    text = resp.content[0].text.strip()
    # strip code fences if present
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.MULTILINE).strip()
    m = re.search(r"\{.*\}", text, re.DOTALL)
    data = json.loads(m.group() if m else text)

    concepts = [
        Concept(
            canonical_name=c["canonical_name"].strip(),
            domain=DOMAIN,
            summary=c.get("summary", ""),
            tags=["podcast", info.id],
            extraction_id=extraction_id,
        )
        for c in data.get("concepts", []) if c.get("canonical_name", "").strip()
    ]
    triplets = []
    for t in data.get("triplets", []):
        try:
            rel = RelationType(t["relation"].strip().upper())
        except Exception:
            rel = RelationType.relates_to
        subj, obj = t.get("subject", "").strip(), t.get("object", "").strip()
        if subj and obj:
            triplets.append(Triplet(subject=subj, relation=rel, object=obj,
                                    extraction_id=extraction_id))
    return concepts, triplets


def forward_to_kg(tr: Transcript, info, transcript_file: str, extraction_id: str) -> dict:
    KG_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    store = SqliteStore(KG_DB_PATH)
    conn = store.connection
    apply_migrations(conn)
    kg = KGStore(conn)

    print("→ Extracting concepts + triplets (Claude)…")
    concepts, triplets = extract_concepts_triplets(tr, info, extraction_id)
    print(f"  extracted {len(concepts)} concepts, {len(triplets)} triplets")

    # Ensure every triplet endpoint is also a concept (FK requires the node to exist)
    known = {c.canonical_name for c in concepts}
    for t in triplets:
        for name in (t.subject, t.object):
            if name not in known:
                known.add(name)
                concepts.append(Concept(canonical_name=name, domain=DOMAIN,
                                        summary="", tags=["podcast", info.id],
                                        extraction_id=extraction_id))

    # Insert nodes (concepts) and resolve authoritative ids
    name_to_id: dict[str, str] = {}
    for c in concepts:
        cid = str(uuid.uuid4())
        store.upsert_concept(id=cid, canonical_name=c.canonical_name,
                             domain=DOMAIN, directory_path=transcript_file)
        row = store.get_concept_by_name(c.canonical_name, DOMAIN)
        name_to_id[c.canonical_name] = row["id"] if row else cid

    # Insert edges (triplets) and approve them into the live graph
    edges, approved, pending = 0, 0, 0
    for t in triplets:
        sid, oid = name_to_id.get(t.subject), name_to_id.get(t.object)
        if not sid or not oid or sid == oid:
            continue
        edge_id = kg.upsert_edge(KGStore.make_edge(sid, t.relation, oid, extraction_id))
        edges += 1
        try:
            kg.update_edge_status(edge_id, "approved")
            approved += 1
        except CycleDetected:
            pending += 1  # left pending; a cycle in a hierarchical relation
    print(f"  ✓ KG: {len(concepts)} nodes, {edges} edges ({approved} approved, {pending} left pending)")
    return {"nodes": len(concepts), "edges": edges, "approved": approved, "pending": pending}


# ── orchestration ─────────────────────────────────────────────────────────────

def run(url: str) -> dict:
    extraction_id = str(uuid.uuid4())
    tr, info = make_transcript(url)
    transcript_file = str((PROJECT_ROOT / "data" / "transcripts" / f"{info.id}.json"))

    print("\n→ Forwarding into stores…")
    mem_path = forward_to_memory(tr, info)
    n_chunks = forward_to_vector(tr, info, transcript_file, extraction_id)
    kg_stats = forward_to_kg(tr, info, transcript_file, extraction_id)

    summary = {
        "episode_id": info.id,
        "title": info.title,
        "memory_file": str(mem_path),
        "vector_chunks": n_chunks,
        **kg_stats,
    }
    print("\n✓ Done.")
    print(json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print('Usage: python scripts/index_transcript.py "<podcast-url>"')
        raise SystemExit(1)
    run(sys.argv[1])
