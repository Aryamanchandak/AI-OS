"""Central configuration for the Podcast Summariser pipeline."""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Absolute project root so the MCP server works regardless of launch cwd.
ROOT = Path(__file__).resolve().parent

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

DEFAULT_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-pro")  # summarisation
TRANSCRIBE_MODEL = os.environ.get("GEMINI_TRANSCRIBE_MODEL", "gemini-2.5-flash")
SEARCH_MODEL = os.environ.get("GEMINI_SEARCH_MODEL", "gemini-2.5-flash")  # grounded YouTube search
AGENT_MODEL = os.environ.get("GEMINI_AGENT_MODEL", "gemini-2.5-flash")  # MCP-client agent loop

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

TMP_AUDIO = ROOT / "tmp/audio"
TMP_TRANSCRIPTS = ROOT / "tmp/transcripts"
OUTPUT_TRANSCRIPTS = ROOT / "output/transcripts"
OUTPUT_SUMMARIES = ROOT / "output/summaries"
OUTPUT_UI = ROOT / "output/ui"
PODCASTS_FILE = ROOT / "podcasts.yaml"

# ---------------------------------------------------------------------------
# Ingest limits
# ---------------------------------------------------------------------------

SUPPORTED_EXTS = {"mp3", "wav", "m4a", "mp4", "ogg", "flac", "aac"}

# ---------------------------------------------------------------------------
# Summary prompt
# ---------------------------------------------------------------------------

SUMMARY_PROMPT = """You are a senior research analyst summarising a podcast episode for a busy
executive who will not listen to it. Your output is the only record of this
conversation they will see.

Episode metadata:
- Title: {title}
- Source: {source_url}
- Duration: {duration_human}
{speaker_count_line}

Transcript:
{transcript}

Produce a Markdown summary with these sections, in order:

## TL;DR
Three sentences. What was the conversation about, what was the central tension
or thesis, and what is the single most important thing the executive should know.

## Main topics
Five to eight bullets. Each bullet is one sentence framing what was discussed.
Order by where in the episode they appeared. Do not editorialise.

## Notable claims & moments
Five to ten bullets. Each bullet starts with the [HH:MM:SS] timestamp from the
transcript where the claim appears. Use the timestamps embedded in the transcript
— do not estimate. Quote or paraphrase tightly. Include claims that are surprising,
contested, predictive, or specific enough to fact-check.

## People & works mentioned
Bullets. Names of people, organisations, books, papers, or products mentioned,
with one-line context for each. Skip the host and guest themselves; this is for
others mentioned in passing.

## What this episode is good for
Two sentences. Who would benefit from listening to the full thing, and who can
safely skip it.

Constraints:
- Be specific. Avoid generalities like "they discussed AI." Always name the
  specific topic, technology, person, or claim.
- Stay under 1500 words total.
- If something cannot be inferred from the transcript, omit it. Never invent.
- Use the same names and terms the speakers use; do not normalise.
"""
