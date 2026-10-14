"""Simple one-shot Obsidian ingestion: vault -> bronze -> ledger.

This replaces the multi-phase inbox/processing/review-cockpit flow for Obsidian
notes. It reads .md files straight from the vault (filtered by
config/obsidian_filters.txt), and captures each new or changed note directly to
immutable bronze via lib capture(). Dedup is by content hash, so:

  - unchanged notes are skipped for free on every run
  - an edited note becomes a NEW bronze item (versioning, never overwrite)
  - lineage (vault path -> content_hash) is recorded in note_lineage

Run it via scripts/ingest_obsidian.sh, or:

    python -m pipeline.core.obsidian [--dry-run] [--vault PATH]
"""

from __future__ import annotations

import argparse
import fnmatch
from pathlib import Path

from .capture import capture
from .ids import content_hash
from .ledger import _conn, get_item, init_ledger
from .obsidian_sync import DEFAULT_OBSIDIAN_CONFIG, discover_vault_path

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_FILTERS = _REPO_ROOT / "config" / "obsidian_filters.txt"


def load_filters(path: Path = DEFAULT_FILTERS) -> tuple[list[str], list[str]]:
    """Parse the filter file into (includes, excludes) glob lists.

    Lines are `include <glob>` or `exclude <glob>` (globs relative to the vault
    root, matched with fnmatch against the posix relative path). `#` comments
    and blank lines are ignored. If any include lines exist, only matching
    paths are considered; excludes always apply afterwards.
    """
    includes: list[str] = []
    excludes: list[str] = []
    if not path.exists():
        return includes, excludes
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        kind, _, pattern = line.partition(" ")
        pattern = pattern.strip()
        if not pattern:
            continue
        if kind == "include":
            includes.append(pattern)
        elif kind == "exclude":
            excludes.append(pattern)
    return includes, excludes


def _matches(rel_posix: str, patterns: list[str]) -> bool:
    return any(
        fnmatch.fnmatch(rel_posix, p) or rel_posix.startswith(p.rstrip("*/") + "/")
        for p in patterns
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


def _ensure_lineage_table() -> None:
    with _conn() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS note_lineage("
            "source_path TEXT, content_hash TEXT, captured_at TEXT)"
        )


def _record_lineage(source_path: str, chash: str, captured_at: str) -> None:
    with _conn() as conn:
        conn.execute(
            "INSERT INTO note_lineage(source_path, content_hash, captured_at) VALUES(?,?,?)",
            (source_path, chash, captured_at),
        )


def ingest(vault: Path | None = None, filters_path: Path = DEFAULT_FILTERS, dry_run: bool = False) -> dict:
    vault = (vault or discover_vault_path(DEFAULT_OBSIDIAN_CONFIG)).expanduser().resolve()
    includes, excludes = load_filters(filters_path)
    init_ledger()
    _ensure_lineage_table()

    stats = {"captured": 0, "skipped_unchanged": 0, "skipped_empty": 0}
    captured_titles: list[str] = []

    for note in candidate_notes(vault, includes, excludes):
        rel = note.relative_to(vault).as_posix()
        body = note.read_text(encoding="utf-8", errors="replace")
        if not body.strip():
            stats["skipped_empty"] += 1
            continue
        if get_item(content_hash(body)):
            stats["skipped_unchanged"] += 1
            continue
        if dry_run:
            stats["captured"] += 1
            captured_titles.append(rel)
            continue
        result = capture(
            source="note",
            content=body,
            metadata={"origin": "obsidian", "source_path": rel, "title": note.stem},
            authored=True,
        )
        if result.duplicate:
            stats["skipped_unchanged"] += 1
            continue
        from datetime import datetime, timezone

        _record_lineage(rel, result.content_hash, datetime.now(timezone.utc).isoformat())
        stats["captured"] += 1
        captured_titles.append(rel)

    stats["vault"] = str(vault)
    stats["notes"] = captured_titles
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest Obsidian notes straight to bronze.")
    parser.add_argument("--vault", type=Path, help="Override the discovered vault path.")
    parser.add_argument("--filters", type=Path, default=DEFAULT_FILTERS, help="Filter file path.")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be captured; write nothing.")
    args = parser.parse_args()

    stats = ingest(vault=args.vault, filters_path=args.filters, dry_run=args.dry_run)
    label = "would capture" if args.dry_run else "captured"
    print(f"vault: {stats['vault']}")
    print(
        f"{label}: {stats['captured']}  "
        f"unchanged: {stats['skipped_unchanged']}  empty: {stats['skipped_empty']}"
    )
    for rel in stats["notes"]:
        print(f"  + {rel}")


if __name__ == "__main__":
    main()
