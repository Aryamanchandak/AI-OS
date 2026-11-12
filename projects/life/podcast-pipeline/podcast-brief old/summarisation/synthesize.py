"""
synthesize.py — Pass 2: build the final research brief using Claude Opus.

Takes the transcript, extracted claims, and research findings, and produces
the polished markdown brief that gets pushed to Reader.
"""

from core.config import MODEL_SYNTHESIS, load_prompt, require_env
from core.llm import call_anthropic
from core.models import ExtractionResult, SurfacedItemWithClaim, Transcript


def synthesize(
    transcript: Transcript,
    extraction: ExtractionResult,
    surfaced_items: list[SurfacedItemWithClaim] | None = None,
    show_name: str = "",
    speakers_hint: str = "",
) -> str:
    """
    Produce the final markdown brief.
    Uses Opus for synthesis — this is the highest-quality pass and worth the cost.
    """
    require_env("ANTHROPIC_API_KEY")

    profile_prompt = load_prompt(extraction.profile)
    research_section = _format_research_mcp(surfaced_items)

    user_message = f"""## Show
{show_name}

## Speakers
{speakers_hint or "Speakers identified in transcript: " + ", ".join(transcript.speakers)}

## Episode description (from extraction pass)
{extraction.episode_description}

---

## Research findings
{research_section}

---

## Full transcript (with speaker labels and timestamps)
{transcript.to_prompt_format(max_chars=170_000)}

---

Now produce the research brief following the structure described in the system instructions. Be rigorous, preserve verbatim quotes, and surface tensions between what was claimed and what the research shows."""

    return call_anthropic(
        model=MODEL_SYNTHESIS,
        max_tokens=8000,
        system=profile_prompt,
        messages=[{"role": "user", "content": user_message}],
    )


def _format_research_mcp(surfaced_items: list[SurfacedItemWithClaim] | None) -> str:
    """Format SurfacedItemWithClaim list for the synthesis prompt."""
    if not surfaced_items:
        return "(No external research was conducted for this brief — synthesis is based on the transcript alone.)"

    sections = []
    for i, item in enumerate(surfaced_items, 1):
        claim = item.claim
        block = [
            f"\n**Research finding {i}** — {claim.speaker} at {claim.timestamp}",
            f"  Claim type: {claim.type}",
            f'  Quote: "{claim.quote}"',
            f"  Summary: {claim.summary}",
            f"  Verdict: correctness={item.triage_correctness}, "
            f"effort={item.triage_effort}, confidence={item.triage_confidence:.2f}",
            f"  Rationale: {item.triage_rationale}",
        ]

        if item.logical_sources:
            block.append(f"  Sources ({len(item.logical_sources)} found, showing top 4):")
            for src in item.logical_sources[:4]:
                authors = ", ".join(src.authors[:2]) if src.authors else "Unknown"
                year = f" ({src.published[:4]})" if src.published else ""
                block.append(f"    - {src.title} — {authors}{year}")
                if src.url:
                    block.append(f"      URL: {src.url}")
                if src.raw_excerpt:
                    block.append(f"      Excerpt: {src.raw_excerpt[:250]}")
        else:
            block.append("  Sources: none found")

        if item.essay_path:
            block.append(f"  Full analysis: {item.essay_path}")

        sections.append("\n".join(block))

    return "\n".join(sections)
