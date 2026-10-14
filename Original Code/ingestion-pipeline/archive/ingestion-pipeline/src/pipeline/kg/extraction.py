"""LLM-based triplet extraction and bronze-file orchestration."""

from __future__ import annotations

import json
import logging
import os
import re
import uuid
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from pipeline.kg.models import Triplet
from pipeline.kg.prompts import EXTRACT_TRIPLETS, EXTRACT_TRIPLETS_RETRY_SUFFIX

if TYPE_CHECKING:
    from pipeline.core.ledger import Item

logger = logging.getLogger(__name__)

# Configurable so a model bump needs no code edit. Override with KG_EXTRACTION_MODEL.
_DEFAULT_MODEL = os.environ.get("KG_EXTRACTION_MODEL", "claude-sonnet-4-6")


class TripletExtractionError(RuntimeError):
    """Raised when triplet extraction cannot complete successfully."""


def _strip_fences(raw: str) -> str:
    """Remove markdown code fences if the model wrapped the JSON in them."""
    raw = raw.strip()
    if raw.startswith("```"):
        lines = raw.splitlines()
        inner = lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
        raw = "\n".join(inner)
    return raw.strip()


def _parse_triplets(raw: str, source: Optional[str]) -> list[Triplet]:
    data = json.loads(_strip_fences(raw))
    if not isinstance(data, list):
        raise ValueError(f"Expected JSON array, got {type(data).__name__}")
    results: list[Triplet] = []
    for item in data:
        subj = str(item.get("subject", "")).strip()
        rel = re.sub(r"[^A-Z0-9_]", "_", str(item.get("relation", "RELATES_TO")).upper().strip())
        obj = str(item.get("object", "")).strip()
        if subj and obj and rel:
            results.append(Triplet(subject=subj, relation=rel, object=obj, source=source))
    return results


def _concept_id(name: str, source_hash: str = "legacy") -> str:
    """Mint a stable per-source ID without claiming cross-source identity."""
    normalized = re.sub(r"\s+", " ", name.casefold().strip()) or "unknown"
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"kg:{source_hash}:{normalized}"))


def _extract_text_triplets(
    text: str,
    source: Optional[str] = None,
    model: str = _DEFAULT_MODEL,
    api_key: Optional[str] = None,
    strict: bool = True,
) -> list[Triplet]:
    """Extract (subject, relation, object) triplets from text using Claude."""
    text = text.strip()
    if not text:
        logger.debug("[Extractor] extract_triplets called with empty text - skipping")
        return []

    logger.info(
        "[Extractor] Extracting triplets from %d chars (source=%r, model=%s)",
        len(text), source, model,
    )

    try:
        import anthropic  # type: ignore[import]
    except ImportError:
        message = (
            "[Extractor] MISSING DEPENDENCY - anthropic package not installed. "
            "Fix: pip install anthropic OR pip install knowledge_graph[extraction]"
        )
        logger.error(message)
        if strict:
            raise TripletExtractionError(message)
        return []

    client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
    prompt = EXTRACT_TRIPLETS.format(text=text)
    last_error: Optional[str] = None

    for attempt in range(2):
        if attempt == 1:
            logger.info("[Extractor] Retrying extraction (attempt 2/2) - previous error: %s", last_error)
        retry_note = (
            EXTRACT_TRIPLETS_RETRY_SUFFIX.format(last_error=last_error)
            if attempt == 1 and last_error
            else ""
        )
        try:
            logger.debug("[Extractor] Calling %s (attempt %d/2)", model, attempt + 1)
            resp = client.messages.create(
                model=model,
                max_tokens=4096,
                temperature=0.1,
                messages=[{"role": "user", "content": prompt + retry_note}],
            )
            raw = resp.content[0].text
            logger.debug("[Extractor] Raw LLM response (%d chars): %s", len(raw), raw[:500])
            triplets = _parse_triplets(raw, source)
            logger.info("[Extractor] Extracted %d triplet(s) from source=%r", len(triplets), source)
            return triplets
        except json.JSONDecodeError as exc:
            last_error = f"JSON parse error: {exc}"
            logger.warning("[Extractor] JSON parse failed (attempt %d/2): %s", attempt + 1, exc)
        except (ValueError, KeyError, IndexError) as exc:
            last_error = f"Parse error: {exc}"
            logger.warning("[Extractor] Parse failed (attempt %d/2): %s", attempt + 1, exc)
        except Exception as exc:
            last_error = str(exc)
            logger.error("[Extractor] Anthropic API call FAILED (attempt %d/2) - %s", attempt + 1, exc)
            break

    message = (
        f"[Extractor] extract_triplets GAVE UP after 2 attempts (source={source!r}). "
        f"Last error: {last_error}."
    )
    logger.error(message)
    if strict:
        raise TripletExtractionError(message)
    return []


def extract_triplets(item: "Item") -> str:
    """
    Idempotent. Reads bronze file, calls Claude, writes triplets JSONL to Raw Data.
    Returns absolute path to the JSONL file.
    Marks ledger stage (kg, extracted).
    """
    from pipeline.core.ledger import is_done, mark

    triplets_path = str(item.triplets_abs())

    if is_done(item.content_hash, "kg", "extracted"):
        logger.info("[Extractor] %s already extracted - reusing %s", item.item_id, triplets_path)
        return triplets_path

    from pipeline.core.bronze import read_body

    body = read_body(item.bronze_abs())

    try:
        triplets = _extract_text_triplets(body, source=item.content_hash, strict=True)
        out = Path(triplets_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", encoding="utf-8") as handle:
            for triplet in triplets:
                handle.write(json.dumps({
                    "subject": _concept_id(triplet.subject, item.content_hash),
                    "subject_name": triplet.subject,
                    "predicate": triplet.relation,
                    "object": _concept_id(triplet.object, item.content_hash),
                    "object_name": triplet.object,
                    "domain": "general",
                    "source_hash": item.content_hash,
                }) + "\n")
        mark(item.content_hash, "kg", "extracted", "done", artifact_path=triplets_path)
        logger.info("[Extractor] %s extracted %d triplets -> %s", item.item_id, len(triplets), triplets_path)
        return triplets_path
    except Exception as exc:
        mark(item.content_hash, "kg", "extracted", "failed", error=str(exc))
        raise
