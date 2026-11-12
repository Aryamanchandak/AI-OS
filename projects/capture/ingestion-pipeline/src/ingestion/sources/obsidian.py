from __future__ import annotations

import fnmatch
import json
import logging
from pathlib import Path
from typing import Any

from ingestion.models import CaptureOutcome, CaptureRequest, UserSelection
from ingestion.normalization import MalformedSourceError
from ingestion.pipeline import UnifiedIngestionPipeline
from ingestion.publish.vault_writer import (
    PAGE_SCANNERS_FOLDER,
    is_book_highlights_doc,
    iter_book_highlight_passages,
)

logger = logging.getLogger(__name__)

DEFAULT_OBSIDIAN_CONFIG = (
    Path.home() / "Library" / "Application Support" / "obsidian" / "obsidian.json"
)
_PACKAGE_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_FILTERS = _PACKAGE_ROOT / "config" / "obsidian_filters.txt"


class ObsidianConfigError(RuntimeError):
    """Raised when the vault path cannot be resolved from obsidian.json."""


class ObsidianFilterError(ValueError):
    """Raised when a filter file rule cannot be parsed. Fails loud, never
    silently ignored, per the Component 8 decision."""


def discover_vault_path(obsidian_config: Path = DEFAULT_OBSIDIAN_CONFIG) -> Path:
    data = json.loads(obsidian_config.expanduser().read_text(encoding="utf-8"))
    vaults = data.get("vaults", {})
    paths: list[Path] = []
    if isinstance(vaults, dict):
        for vault in vaults.values():
            if isinstance(vault, dict) and isinstance(vault.get("path"), str):
                paths.append(Path(vault["path"]).expanduser())
    if not paths:
        raise ObsidianConfigError(f"No vault path found in {obsidian_config}")
    for path in paths:
        if path.exists():
            return path.resolve()
    return paths[0].resolve()


def load_filters(path: Path = DEFAULT_FILTERS) -> tuple[list[str], list[str]]:
    """Parse the filter file into (includes, excludes) glob lists.

    Lines are `include <glob>` or `exclude <glob>` (globs relative to the vault
    root, matched with fnmatch against the posix relative path). `#` comments
    and blank lines are ignored. Any other non-blank line is a configuration
    error, not a silently skipped rule.
    """
    includes: list[str] = []
    excludes: list[str] = []
    if not path.exists():
        return includes, excludes
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        kind, _, pattern = line.partition(" ")
        pattern = pattern.strip()
        if kind not in {"include", "exclude"} or not pattern:
            raise ObsidianFilterError(f"Malformed filter rule at {path}:{line_number}: {raw!r}")
        if kind == "include":
            includes.append(pattern)
        else:
            excludes.append(pattern)
    return includes, excludes


def _matches(rel_posix: str, patterns: list[str]) -> bool:
    return any(
        fnmatch.fnmatch(rel_posix, pattern) or rel_posix.startswith(pattern.rstrip("*/") + "/")
        for pattern in patterns
    )


def candidate_notes(vault: Path, includes: list[str], excludes: list[str]) -> list[Path]:
    notes = []
    for path in sorted(vault.rglob("*.md")):
        if not path.is_file():
            continue
        rel = path.relative_to(vault).as_posix()
        if includes and not _matches(rel, includes):
            continue
        if _matches(rel, excludes):
            continue
        notes.append(path)
    return notes


def capture_obsidian_vault(
    pipeline: UnifiedIngestionPipeline,
    *,
    vault: Path | None = None,
    filters_path: Path = DEFAULT_FILTERS,
    obsidian_config: Path = DEFAULT_OBSIDIAN_CONFIG,
    source_type: str = "obsidian_note",
    metadata: dict[str, Any] | None = None,
) -> list[CaptureOutcome]:
    """Discover and directly capture Obsidian notes.

    Each selected note is passed straight to pipeline.capture() -- there is no
    separate ledger or note_lineage table here; the merged store already
    records origin, normalized origin, versions, captures, and supersession.
    """
    resolved_vault = (vault or discover_vault_path(obsidian_config)).expanduser().resolve()
    if not resolved_vault.is_dir():
        raise NotADirectoryError(f"Obsidian vault not found: {resolved_vault}")
    includes, excludes = load_filters(filters_path)
    outcomes: list[CaptureOutcome] = []
    for note in candidate_notes(resolved_vault, includes, excludes):
        relative = note.relative_to(resolved_vault).as_posix()
        try:
            content = note.read_bytes()
        except OSError as exc:
            # One unreadable note must not stop the rest of the vault from
            # being captured -- it's simply not in this run's batch and will
            # be retried the next time this runs (nothing was written for it).
            logger.warning("Skipping unreadable note %s: %s", note, exc)
            continue
        try:
            text = content.decode("utf-8", errors="ignore")
            is_page_scanner_note = any(
                line.strip().startswith("page_scanner_id:") for line in text.splitlines()
            )
            if is_page_scanner_note or is_book_highlights_doc(text):
                # T63: a page-scanner note's marked passages, and the book
                # highlights document they accumulate into, are captured one
                # passage at a time by capture_book_highlights() instead --
                # not as a whole document handed to the segmentation model.
                continue
            outcome = pipeline.capture(
                CaptureRequest(
                    source_type=source_type,
                    origin=str(note.resolve()),
                    content=content,
                    metadata={
                        **(metadata or {}),
                        "vault_relative_path": relative,
                        "note_title": note.stem,
                        "origin_kind": "obsidian_note",
                    },
                )
            )
        except MalformedSourceError as exc:
            # pipeline.capture() already quarantined it; don't let one bad
            # note abort every other note in the vault.
            logger.warning("Skipping malformed note %s: %s", note, exc)
            continue
        outcomes.append(outcome)
    return outcomes


def capture_book_highlights(
    pipeline: UnifiedIngestionPipeline,
    *,
    vault: Path | None = None,
    obsidian_config: Path = DEFAULT_OBSIDIAN_CONFIG,
    source_type: str = "obsidian_note",
    metadata: dict[str, Any] | None = None,
) -> list[CaptureOutcome]:
    """Capture each book page as one parent with explicit highlight spans.

    T63's settled direction for how a photo's highlighted passages become
    highlights: `publish.vault_writer.append_book_highlight_passages()`
    accumulates each approved photo's passages into one document per book as
    they are approved; this reads that document back and captures each
    page section as one source with multiple `user_selection` boundaries.  The
    passages become sibling highlights without model segmentation.  Keeping
    the page as their parent is essential: equal text on two different pages
    must remain two different highlights with two different provenances.
    """
    resolved_vault = (vault or discover_vault_path(obsidian_config)).expanduser().resolve()
    if not resolved_vault.is_dir():
        raise NotADirectoryError(f"Obsidian vault not found: {resolved_vault}")
    outcomes: list[CaptureOutcome] = []
    scanners_root = resolved_vault / PAGE_SCANNERS_FOLDER
    if not scanners_root.is_dir():
        return outcomes
    for doc_path in sorted(scanners_root.glob("*/*-highlights.md")):
        relative = doc_path.relative_to(resolved_vault).as_posix()
        try:
            passages = iter_book_highlight_passages(doc_path)
        except OSError as exc:
            logger.warning("Skipping unreadable book highlights doc %s: %s", doc_path, exc)
            continue
        by_page: dict[int, list[Any]] = {}
        for passage in passages:
            by_page.setdefault(passage.page_scanner_id, []).append(passage)
        for page_id, page_passages in by_page.items():
            # The page id is part of the immutable captured content as well as
            # its origin.  Global content-hash dedup therefore cannot collapse
            # two different pages that happen to quote identical wording.
            page_content = f"page_scanner_id: {page_id}\n\n"
            selections: list[UserSelection] = []
            for passage in page_passages:
                start = len(page_content)
                page_content += passage.text
                end = len(page_content)
                page_content += "\n\n"
                selections.append(
                    UserSelection(
                        parent_source_ref=(
                            f"{relative}#page-scanner-passage-{passage.passage_id}"
                        ),
                        parent_start_char=passage.parent_start_char,
                        parent_end_char=passage.parent_end_char,
                        source_start_char=start,
                        source_end_char=end,
                    )
                )
            origin = f"{doc_path.resolve()}#page-scanner-{page_id}"
            try:
                outcome = pipeline.capture(
                    CaptureRequest(
                        source_type=source_type,
                        origin=origin,
                        content=page_content,
                        boundary_origin="user_selection",
                        user_selections=selections,
                        metadata={
                            **(metadata or {}),
                            "vault_relative_path": relative,
                            "note_title": doc_path.stem,
                            "origin_kind": "page_scanner",
                            "page_scanner_id": page_id,
                            "passage_ids": [
                                passage.passage_id for passage in page_passages
                            ],
                            "passage_count": len(page_passages),
                        },
                    )
                )
            except MalformedSourceError as exc:
                logger.warning(
                    "Skipping malformed page %s in %s: %s",
                    page_id,
                    doc_path,
                    exc,
                )
                continue
            outcomes.append(outcome)
    return outcomes
