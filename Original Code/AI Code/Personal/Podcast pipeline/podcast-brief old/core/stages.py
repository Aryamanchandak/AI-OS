"""
stages.py — Disk-keyed stage functions.

Each stage takes an episode_id (+ minimal params), re-loads its inputs from disk,
runs its processing, persists its output, and returns a compact Pydantic *Result.
These are the building blocks for both the orchestrator and the per-stage MCP tools.

No Rich console output — all status is returned in the result models so callers
can render it however they like (Rich CLI, MCP tool response, log, etc.).
"""

from pathlib import Path

from core.config import (
    AUDIO_DIR, TRANSCRIPT_DIR, BRIEF_DIR, EXTRACTION_DIR, RESEARCH_DIR,
    ensure_dirs, load_shows,
)
from core.models import (
    DeliverResult, ExtractResult, IngestResult, ResearchResult,
    SynthesizeResult, TranscribeResult,
)
from core import state


# ─── 1. Ingest ────────────────────────────────────────────────────────────────

def stage_ingest(
    url: str,
    show_name: str = "Manual entry",
    profile: str = "hybrid",
    title: str = "",
) -> IngestResult:
    """
    Download audio and register the episode in the DB.
    Idempotent — re-running on a cached episode just returns IngestResult with
    already_processed=True if it previously completed.
    """
    ensure_dirs()
    state.init_db()

    from ingestion.ingest import fetch_audio
    info = fetch_audio(url, title)

    already_processed = state.episode_exists(info.id)

    try:
        audio_size_mb = info.audio_path.stat().st_size / (1024 * 1024)
    except Exception:
        audio_size_mb = 0.0

    if not already_processed:
        state.create_episode(info.id, show_name, info.title, info.source_url, profile)
        state.update_episode(info.id, audio_path=str(info.audio_path), status="pending")

    return IngestResult(
        episode_id=info.id,
        title=info.title,
        audio_path=info.audio_path,
        audio_size_mb=audio_size_mb,
        already_processed=already_processed,
    )


# ─── 2. Transcribe ────────────────────────────────────────────────────────────

def stage_transcribe(
    episode_id: str,
    speakers_hint: str = "",
    force: bool = False,
) -> TranscribeResult:
    """Transcribe audio for episode_id. Audio must exist at AUDIO_DIR/<id>.mp3."""
    ensure_dirs()

    audio_path = AUDIO_DIR / f"{episode_id}.mp3"
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio not found: {audio_path}. Run stage_ingest first.")

    from transcription.transcribe import transcribe
    tr = transcribe(audio_path, episode_id, speakers_hint=speakers_hint or None, force=force)

    cache_path = TRANSCRIPT_DIR / f"{episode_id}.json"

    return TranscribeResult(
        episode_id=episode_id,
        duration_seconds=tr.duration_seconds,
        segment_count=len(tr.segments),
        speakers=tr.speakers,
        transcript_path=str(cache_path),
    )


# ─── 3. Extract claims ────────────────────────────────────────────────────────

def stage_extract(episode_id: str) -> ExtractResult:
    """
    Extract claims from the cached transcript.
    profile and show_name are read from the episodes DB record.
    """
    ensure_dirs()

    tr_path = TRANSCRIPT_DIR / f"{episode_id}.json"
    if not tr_path.exists():
        raise FileNotFoundError(f"Transcript not found: {tr_path}. Run stage_transcribe first.")

    ep = state.get_episode(episode_id)
    profile = (ep or {}).get("profile", "hybrid")
    show_name = (ep or {}).get("show_name", "Unknown show")

    from core.models import Transcript
    from extraction.extract import extract_claims
    tr = Transcript.load(tr_path)
    result = extract_claims(tr, profile, show_name)

    claims_by_type: dict[str, int] = {}
    for c in result.claims:
        claims_by_type[c.type] = claims_by_type.get(c.type, 0) + 1

    out_path = EXTRACTION_DIR / f"{episode_id}.json"

    return ExtractResult(
        episode_id=episode_id,
        claim_count=len(result.claims),
        episode_description=result.episode_description,
        extraction_path=str(out_path),
        claims_by_type=claims_by_type,
    )


# ─── 4. Research claims ───────────────────────────────────────────────────────

def stage_research(episode_id: str) -> ResearchResult:
    """
    Research claims via Research_MCP. Loads ExtractionResult from disk,
    runs research (via ThreadPoolExecutor to stay asyncio-safe), persists results.
    """
    ensure_dirs()

    ext_path = EXTRACTION_DIR / f"{episode_id}.json"
    if not ext_path.exists():
        raise FileNotFoundError(f"Extraction not found: {ext_path}. Run stage_extract first.")

    from core.models import ExtractionResult
    extraction = ExtractionResult.load(ext_path)

    from research.mcp_bridge import research_claims_via_mcp, save_research
    surfaced_items, research_run_id = research_claims_via_mcp(extraction.claims)

    research_path = save_research(episode_id, surfaced_items)

    deep_count = sum(1 for i in surfaced_items if i.triage_effort == "deep")
    light_count = sum(1 for i in surfaced_items if i.triage_effort == "light")

    return ResearchResult(
        episode_id=episode_id,
        surfaced_count=len(surfaced_items),
        deep_count=deep_count,
        light_count=light_count,
        research_run_id=research_run_id or "",
        research_path=str(research_path),
    )


# ─── 5. Synthesize brief ──────────────────────────────────────────────────────

def stage_synthesize(episode_id: str) -> SynthesizeResult:
    """
    Synthesize the final markdown brief from transcript + extraction + research.
    All inputs are loaded from disk. show_name/speakers_hint come from DB + shows.yaml.
    """
    ensure_dirs()

    tr_path = TRANSCRIPT_DIR / f"{episode_id}.json"
    ext_path = EXTRACTION_DIR / f"{episode_id}.json"
    if not tr_path.exists():
        raise FileNotFoundError(f"Transcript not found: {tr_path}.")
    if not ext_path.exists():
        raise FileNotFoundError(f"Extraction not found: {ext_path}.")

    from core.models import ExtractionResult, Transcript
    tr = Transcript.load(tr_path)
    extraction = ExtractionResult.load(ext_path)

    ep = state.get_episode(episode_id)
    show_name = (ep or {}).get("show_name", "Unknown show")

    speakers_hint = ""
    for show in load_shows():
        if show.name == show_name:
            speakers_hint = show.speakers_hint
            break

    surfaced_items = []
    res_path = RESEARCH_DIR / f"{episode_id}.json"
    if res_path.exists():
        from research.mcp_bridge import load_research
        surfaced_items = load_research(episode_id)

    from summarisation.synthesize import synthesize
    markdown_brief = synthesize(
        transcript=tr,
        extraction=extraction,
        surfaced_items=surfaced_items,
        show_name=show_name,
        speakers_hint=speakers_hint,
    )

    brief_path = BRIEF_DIR / f"{episode_id}.md"
    brief_path.write_text(markdown_brief)

    return SynthesizeResult(
        episode_id=episode_id,
        char_count=len(markdown_brief),
        brief_path=str(brief_path),
    )


# ─── 6. Deliver ───────────────────────────────────────────────────────────────

def stage_deliver(episode_id: str, transcript_only: bool = False) -> DeliverResult:
    """
    Format the brief or transcript to HTML and push to Readwise Reader.
    All metadata is loaded from the DB. Content is loaded from BRIEF_DIR / TRANSCRIPT_DIR.
    """
    ensure_dirs()

    ep = state.get_episode(episode_id)
    if not ep:
        raise ValueError(f"Episode {episode_id} not found in DB. Run stage_ingest first.")

    title = ep.get("title") or episode_id
    source_url = ep.get("source_url") or ""
    show_name = ep.get("show_name") or "Unknown show"
    profile = ep.get("profile") or "hybrid"

    from summarisation import format as fmt
    from delivery import deliver

    if transcript_only:
        tr_path = TRANSCRIPT_DIR / f"{episode_id}.json"
        if not tr_path.exists():
            raise FileNotFoundError(f"Transcript not found: {tr_path}.")
        from core.models import Transcript
        tr = Transcript.load(tr_path)
        html_doc = fmt.transcript_to_html(tr, title, source_url, show_name)
        brief_path = BRIEF_DIR / f"{episode_id}_transcript.html"
        brief_path.write_text(html_doc)
        deliver_title = f"📝 Transcript: {title}"
        tags = ["podcast", "transcript", f"podcast/{_slug(show_name)}"]
        summary = f"Full transcript of {title}."
    else:
        md_path = BRIEF_DIR / f"{episode_id}.md"
        if not md_path.exists():
            raise FileNotFoundError(f"Brief markdown not found: {md_path}. Run stage_synthesize first.")

        ext_path = EXTRACTION_DIR / f"{episode_id}.json"
        episode_description = ""
        if ext_path.exists():
            from core.models import ExtractionResult
            extraction = ExtractionResult.load(ext_path)
            episode_description = extraction.episode_description

        markdown_brief = md_path.read_text()
        html_doc = fmt.brief_to_html(
            markdown_text=markdown_brief,
            title=title,
            source_url=source_url,
            show_name=show_name,
            profile=profile,
        )
        brief_path = BRIEF_DIR / f"{episode_id}.html"
        brief_path.write_text(html_doc)
        deliver_title = f"🎙️ {title}"
        tags = ["podcast", f"podcast/{_slug(show_name)}", f"profile/{profile}"]
        summary = episode_description

    result = deliver.push_to_reader(
        html=html_doc,
        title=deliver_title,
        source_url=source_url,
        author=show_name,
        tags=tags,
        location="new",
        summary=summary,
    )

    return DeliverResult(
        episode_id=episode_id,
        reader_url=result["url"],
        brief_path=str(brief_path),
        transcript_only=transcript_only,
    )


def _slug(name: str) -> str:
    return "".join(c.lower() if c.isalnum() else "-" for c in name).strip("-")
