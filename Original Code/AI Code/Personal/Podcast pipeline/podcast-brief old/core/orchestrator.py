"""
orchestrator.py — In-code, fixed-order episode orchestration.

process_episode() calls each stage function in the canonical order, one by one,
in plain Python. The sequence is never left to a model or prompt.

Console output goes to stderr so this module is safe in both CLI and MCP stdio
transport contexts (stdout must remain clean for the JSON-RPC channel).
"""

import sys
from typing import Optional

from rich.console import Console

from core import state
from core.config import ShowConfig, ensure_dirs
from core.stages import (
    stage_deliver,
    stage_extract,
    stage_ingest,
    stage_research,
    stage_synthesize,
    stage_transcribe,
)

console = Console(stderr=True)


def process_episode(
    url: str,
    show: Optional[ShowConfig] = None,
    profile: str = "hybrid",
    speakers_hint: str = "",
    show_name: str = "Manual entry",
    transcript_only: bool = False,
    skip_research: bool = False,
) -> dict:
    """
    Run the full pipeline on a URL in a fixed, deterministic stage order.
    Returns a summary dict. Raises on fatal stage errors (transcribe/extract/synthesize/deliver).
    Research failure degrades gracefully (warns and continues without research data).
    """
    ensure_dirs()
    state.init_db()

    if show:
        profile = show.profile
        speakers_hint = show.speakers_hint
        show_name = show.name

    # ── 1. Ingest ──
    console.print(f"[bold cyan]→ Fetching audio from[/bold cyan] {url}")
    ingest_result = stage_ingest(url, show_name=show_name, profile=profile)
    episode_id = ingest_result.episode_id

    console.print(f"  Episode ID: [green]{episode_id}[/green]")
    console.print(f"  Title: {ingest_result.title}")
    console.print(f"  Audio: {ingest_result.audio_path} ({ingest_result.audio_size_mb:.1f} MB)")

    if ingest_result.already_processed:
        console.print(f"[yellow]⚠ Episode already processed. Use --force to redo.[/yellow]")
        return {"skipped": True, "episode_id": episode_id}

    # ── 2. Transcribe ──
    state.update_episode(episode_id, status="transcribing")
    state.log_run(episode_id, "transcribe", "started")
    console.print(f"\n[bold cyan]→ Transcribing[/bold cyan] (Deepgram Nova-3)")
    try:
        tr_result = stage_transcribe(episode_id, speakers_hint=speakers_hint)
    except Exception as e:
        state.mark_failed(episode_id, f"transcribe: {e}")
        state.log_run(episode_id, "transcribe", "failed", str(e))
        raise

    console.print(f"  Duration: {tr_result.duration_seconds / 60:.1f} min")
    console.print(f"  Segments: {tr_result.segment_count}")
    console.print(f"  Speakers: {', '.join(tr_result.speakers)}")
    state.log_run(
        episode_id, "transcribe", "completed",
        f"{tr_result.segment_count} segments, {len(tr_result.speakers)} speakers",
    )

    # ── Transcript-only path ──
    if transcript_only:
        console.print(f"\n[bold cyan]→ Transcript-only mode — delivering[/bold cyan]")
        state.log_run(episode_id, "deliver", "started")
        try:
            del_result = stage_deliver(episode_id, transcript_only=True)
        except Exception as e:
            state.mark_failed(episode_id, f"deliver: {e}")
            state.log_run(episode_id, "deliver", "failed", str(e))
            raise
        state.mark_completed(episode_id, del_result.reader_url, del_result.brief_path)
        state.log_run(episode_id, "deliver", "completed", del_result.reader_url)
        console.print(f"\n[bold green]✓ Transcript delivered to Reader[/bold green]")
        console.print(f"  URL: {del_result.reader_url}")
        return {
            "episode_id": episode_id,
            "reader_url": del_result.reader_url,
            "transcript_only": True,
        }

    # ── 3. Extract claims ──
    state.update_episode(episode_id, status="extracting")
    state.log_run(episode_id, "extract", "started")
    console.print(f"\n[bold cyan]→ Extracting claims[/bold cyan] (Claude Sonnet)")
    try:
        ext_result = stage_extract(episode_id)
    except Exception as e:
        state.mark_failed(episode_id, f"extract: {e}")
        state.log_run(episode_id, "extract", "failed", str(e))
        raise

    console.print(f"  Claims extracted: {ext_result.claim_count}")
    for claim_type, n in sorted(ext_result.claims_by_type.items(), key=lambda x: -x[1]):
        console.print(f"    {claim_type}: {n}")
    state.log_run(episode_id, "extract", "completed", f"{ext_result.claim_count} claims")

    # ── 4. Research ──
    if not skip_research:
        state.update_episode(episode_id, status="researching")
        state.log_run(episode_id, "research", "started")
        console.print(f"\n[bold cyan]→ Researching claims[/bold cyan] (Research_MCP)")
        try:
            res_result = stage_research(episode_id)
            console.print(
                f"  {res_result.surfaced_count} claims researched "
                f"({res_result.deep_count} deep, {res_result.light_count} light)"
            )
            if res_result.research_run_id:
                state.update_episode(episode_id, research_run_id=res_result.research_run_id)
            state.log_run(
                episode_id, "research", "completed",
                f"{res_result.surfaced_count} items run_id={res_result.research_run_id}",
            )
        except Exception as e:
            console.print(f"  [red]Research failed (continuing without research data): {e}[/red]")
            state.log_run(episode_id, "research", "completed", f"failed: {e}")
    else:
        console.print("\n[yellow]⚠ Skipping research stage (skip_research=True)[/yellow]")

    # ── 5. Synthesize ──
    state.update_episode(episode_id, status="synthesizing")
    state.log_run(episode_id, "synthesize", "started")
    console.print(f"\n[bold cyan]→ Synthesizing brief[/bold cyan] (Claude Opus)")
    try:
        syn_result = stage_synthesize(episode_id)
    except Exception as e:
        state.mark_failed(episode_id, f"synthesize: {e}")
        state.log_run(episode_id, "synthesize", "failed", str(e))
        raise

    console.print(f"  Brief: {syn_result.char_count} chars")
    state.log_run(episode_id, "synthesize", "completed", f"{syn_result.char_count} chars")

    # ── 6. Deliver ──
    state.update_episode(episode_id, status="delivering")
    state.log_run(episode_id, "deliver", "started")
    console.print(f"\n[bold cyan]→ Pushing to Readwise Reader[/bold cyan]")
    try:
        del_result = stage_deliver(episode_id, transcript_only=False)
    except Exception as e:
        state.mark_failed(episode_id, f"deliver: {e}")
        state.log_run(episode_id, "deliver", "failed", str(e))
        raise

    state.mark_completed(episode_id, del_result.reader_url, del_result.brief_path)
    state.log_run(episode_id, "deliver", "completed", del_result.reader_url)

    console.print(f"\n[bold green]✓ Brief delivered to Reader[/bold green]")
    console.print(f"  URL: [link]{del_result.reader_url}[/link]")

    return {
        "episode_id": episode_id,
        "title": ingest_result.title,
        "reader_url": del_result.reader_url,
        "brief_path": del_result.brief_path,
        "claims_count": ext_result.claim_count,
    }
