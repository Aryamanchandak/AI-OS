"""FastMCP server — the tool layer for the agentic podcast pipeline.

Every logical step is an MCP tool over `pipeline.py`. Large intermediate text
(transcripts, summaries) is passed between tools by **file reference**, never inlined,
so the driving agent's context stays small regardless of episode length.

The final UI is rendered with Prefab:
  - `render_summary_ui` returns a live PrefabApp (app=True) so the browser renders
    Summary / Transcript / Metadata tabs directly. A self-contained HTML file is also
    written to output/ui/ as a side effect for offline viewing.
  - `browse_history` shows a searchable DataTable of past summaries (app=True).
  - `GenerativeUI` is also registered so the agent can compose ad-hoc Prefab interfaces.

Run (browser UI):  fastmcp dev server.py
Run (stdio agent): python server.py
"""
import re
from pathlib import Path

from fastmcp import FastMCP
from fastmcp.apps.generative import GenerativeUI
from prefab_ui.app import PrefabApp
from prefab_ui.components import (
    Badge, Column, DataTable, DataTableColumn, Heading,
    Markdown, Metric, Muted, Row, Tab, Tabs, Textarea,
)

import pipeline
from config import OUTPUT_SUMMARIES, OUTPUT_UI, TMP_TRANSCRIPTS

mcp = FastMCP("Podcast Summariser")

# Working dir for intermediate transcript/summary text passed between tools by path.
WORK = TMP_TRANSCRIPTS / "work"
WORK.mkdir(parents=True, exist_ok=True)
OUTPUT_UI.mkdir(parents=True, exist_ok=True)


def _write_ref(name: str, text: str) -> str:
    path = WORK / name
    path.write_text(text)
    return str(path)


def _read_ref(ref: str) -> str:
    return Path(ref).read_text()


# =============================================================================
# Discovery
# =============================================================================

@mcp.tool
def list_podcasts() -> list[dict]:
    """List the configured podcasts (name + RSS feed) from podcasts.yaml."""
    return pipeline.load_podcasts()


@mcp.tool
def get_latest_rss_episode(rss_url: str) -> dict:
    """Fetch the latest episode's metadata from an RSS feed.

    Returns title, published, duration_seconds, and audio_url. If audio_url is null,
    the feed has no downloadable audio — call find_youtube_episode as a fallback.
    """
    return pipeline.get_latest_episode(rss_url)


@mcp.tool
def find_youtube_episode(podcast_name: str, episode_title: str = "") -> dict:
    """Find the latest episode on YouTube via Gemini grounded search. Returns {url}.

    Use this only when get_latest_rss_episode returns a null audio_url.
    """
    return pipeline.find_youtube_episode(podcast_name, episode_title)


# =============================================================================
# Ingest → transcribe → summarise (text passed by file reference)
# =============================================================================

@mcp.tool
def download_audio(url: str) -> dict:
    """Download episode audio (routes YouTube vs direct enclosure automatically).

    Returns {audio_path, title, duration_seconds, source_url, source_type}.
    """
    meta = pipeline.download_audio(url)
    return {
        "audio_path": meta["path"],
        "title": meta["title"],
        "duration_seconds": meta["duration_seconds"],
        "source_url": meta["source_url"],
        "source_type": meta["source_type"],
    }


@mcp.tool
def transcribe_audio(audio_path: str) -> dict:
    """Transcribe audio with Gemini. Writes the transcript to a file and returns a
    reference (the full text is NOT inlined, to keep agent context small).

    Returns {transcript_ref, char_count, cached}.
    """
    tr = pipeline.transcribe(audio_path)
    ref = _write_ref(f"{Path(audio_path).stem}_transcript.txt", tr["text"])
    return {"transcript_ref": ref, "char_count": len(tr["text"]), "cached": tr["cached"]}


@mcp.tool
def summarise_transcript(
    transcript_ref: str,
    title: str,
    source_url: str = "",
    duration_seconds: float = 0.0,
) -> dict:
    """Summarise a transcript (referenced by file) with Gemini. Returns {summary_ref, char_count}."""
    transcript = _read_ref(transcript_ref)
    summary = pipeline.summarise(transcript, title, source_url, duration_seconds)
    ref = _write_ref(Path(transcript_ref).name.replace("_transcript", "_summary"), summary)
    return {"summary_ref": ref, "char_count": len(summary)}


# =============================================================================
# Persist + render
# =============================================================================

@mcp.tool
def save_outputs(
    podcast_name: str, episode_title: str, transcript_ref: str, summary_ref: str
) -> dict:
    """Persist the transcript and summary as markdown under output/. Returns saved paths + slug."""
    return pipeline.save_outputs(
        podcast_name, episode_title, _read_ref(transcript_ref), _read_ref(summary_ref)
    )


@mcp.tool(app=True)
def render_summary_ui(
    podcast_name: str,
    episode_title: str,
    summary_ref: str,
    transcript_ref: str,
    source_url: str = "",
    duration_seconds: float = 0.0,
    speaker_count: int = 0,
    model: str = "",
) -> PrefabApp:
    """Render a Prefab UI (Summary / Transcript / Metadata tabs) in the browser.

    Also writes a self-contained HTML file to output/ui/ for offline viewing.
    """
    summary_md = _read_ref(summary_ref)
    transcript_text = _read_ref(transcript_ref)
    mins = f"{duration_seconds / 60:.0f} min" if duration_seconds else "—"

    with PrefabApp(title=episode_title or podcast_name) as app:
        with Column(gap=4, css_class="p-6 max-w-4xl mx-auto"):
            Heading(episode_title or "Podcast summary")
            with Row(gap=2, css_class="mb-2"):
                Badge(podcast_name)
                if source_url:
                    Badge(source_url[:60], css_class="font-mono text-xs")

            # Key metrics above the tabs
            with Row(gap=6, css_class="mb-4"):
                Metric(label="Duration", value=mins)
                Metric(label="Model", value=model or "—")
                if speaker_count:
                    Metric(label="Speakers", value=str(speaker_count))

            with Tabs():
                with Tab(title="📝 Summary"):
                    Markdown(summary_md)
                with Tab(title="📜 Transcript"):
                    Textarea(value=transcript_text, rows=28, css_class="w-full font-mono text-sm")
                with Tab(title="ℹ️ Metadata"):
                    with Column(gap=3):
                        Markdown(
                            f"**Episode:** {episode_title or '—'}\n\n"
                            f"**Podcast:** {podcast_name or '—'}\n\n"
                            f"**Source:** {source_url or '—'}\n\n"
                            f"**Duration:** {mins}\n\n"
                            f"**Model:** `{model or '—'}`"
                            + (f"\n\n**Speakers identified:** {speaker_count}" if speaker_count else "")
                        )

    # Side-effect: write static HTML for offline viewing
    slug = pipeline.output_slug(podcast_name, episode_title)
    html_path = OUTPUT_UI / f"{slug}.html"
    html_path.write_text(app.html())

    return app


@mcp.tool(app=True)
def browse_history() -> DataTable:
    """Browse previously generated podcast summaries as a searchable, sortable table."""
    files = sorted(
        OUTPUT_SUMMARIES.glob("*_summary.md"),
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )[:50]

    rows = []
    for f in files:
        lines = f.read_text().splitlines()
        episode = lines[0].lstrip("# ").strip() if lines else f.stem
        podcast = "—"
        generated = "—"
        for line in lines[:8]:
            if line.startswith("**Podcast:**"):
                podcast = line.replace("**Podcast:**", "").strip().rstrip("  ")
            elif line.startswith("**Generated:**"):
                generated = line.replace("**Generated:**", "").strip().rstrip("  ")
        rows.append({
            "generated": generated,
            "podcast": podcast,
            "episode": episode,
            "file": f.name,
        })

    return DataTable(
        columns=[
            DataTableColumn(key="generated", header="Date", sortable=True, width="160px"),
            DataTableColumn(key="podcast", header="Podcast", sortable=True, width="200px"),
            DataTableColumn(key="episode", header="Episode"),
            DataTableColumn(key="file", header="File", width="260px"),
        ],
        rows=rows,
        search=True,
    )


# Generative UI capability: lets the agent compose ad-hoc Prefab interfaces.
mcp.add_provider(GenerativeUI())


if __name__ == "__main__":
    mcp.run()
