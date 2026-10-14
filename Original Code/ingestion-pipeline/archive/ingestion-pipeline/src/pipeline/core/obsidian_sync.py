"""LEGACY - kept for the review-cockpit flow (Page Scanner UI).

The simple Obsidian path is pipeline.core.obsidian; this module only mirrors
the vault into inbox/ and claims files into processing/ for manual review.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path


DEFAULT_OBSIDIAN_CONFIG = (
    Path.home() / "Library" / "Application Support" / "obsidian" / "obsidian.json"
)


@dataclass(frozen=True)
class SyncStats:
    mirrored: int = 0
    mirror_skipped: int = 0
    claimed: int = 0
    claim_skipped_unchanged: int = 0
    claim_skipped_duplicate: int = 0

    def add(self, other: "SyncStats") -> "SyncStats":
        return SyncStats(
            mirrored=self.mirrored + other.mirrored,
            mirror_skipped=self.mirror_skipped + other.mirror_skipped,
            claimed=self.claimed + other.claimed,
            claim_skipped_unchanged=(
                self.claim_skipped_unchanged + other.claim_skipped_unchanged
            ),
            claim_skipped_duplicate=(
                self.claim_skipped_duplicate + other.claim_skipped_duplicate
            ),
        )


def configure_raw_data_root(raw_data_root: Path | None) -> Path:
    if raw_data_root is None:
        from .config import RAW_DATA_ROOT as _default_root

        raw_data_root = _default_root

    root = raw_data_root.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    os.environ["RAW_DATA_ROOT"] = str(root)
    return root


def discover_vault_path(obsidian_config: Path = DEFAULT_OBSIDIAN_CONFIG) -> Path:
    data = json.loads(obsidian_config.expanduser().read_text(encoding="utf-8"))
    vaults = data.get("vaults", {})
    paths: list[Path] = []

    if isinstance(vaults, dict):
        for vault in vaults.values():
            if isinstance(vault, dict) and isinstance(vault.get("path"), str):
                paths.append(Path(vault["path"]).expanduser())

    if not paths:
        raise RuntimeError(f"No vault path found in {obsidian_config}")

    for path in paths:
        if path.exists():
            return path.resolve()
    return paths[0].resolve()


def iter_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted(path for path in root.rglob("*") if path.is_file())


def bytes_equal(left: Path, right: Path) -> bool:
    if not left.exists() or not right.exists():
        return False
    if left.stat().st_size != right.stat().st_size:
        return False

    with left.open("rb") as left_file, right.open("rb") as right_file:
        while True:
            left_chunk = left_file.read(1024 * 1024)
            right_chunk = right_file.read(1024 * 1024)
            if left_chunk != right_chunk:
                return False
            if not left_chunk:
                return True


def mirror_vault_to_inbox(vault_root: Path, inbox_root: Path) -> SyncStats:
    vault_root = vault_root.expanduser().resolve()
    inbox_root.mkdir(parents=True, exist_ok=True)
    stats = SyncStats()

    for source in iter_files(vault_root):
        relative = source.relative_to(vault_root)
        destination = inbox_root / relative
        if bytes_equal(source, destination):
            stats = stats.add(SyncStats(mirror_skipped=1))
            continue

        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        stats = stats.add(SyncStats(mirrored=1))

    return stats


def working_name(source_path: Path) -> str:
    normalized = str(source_path.expanduser().resolve())
    path_fingerprint = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]
    stem = source_path.stem.lower()
    safe_stem = "".join(char if char.isalnum() else "-" for char in stem).strip("-")
    safe_stem = safe_stem[:60] or "item"
    return f"{safe_stem}--{path_fingerprint}{source_path.suffix.lower()}"


def processing_has_same_bytes(candidate: Path, processing_root: Path) -> bool:
    for working_file in iter_files(processing_root):
        if bytes_equal(candidate, working_file):
            return True
    return False


def claim_candidates(inbox_roots: list[Path], processing_root: Path) -> SyncStats:
    processing_root.mkdir(parents=True, exist_ok=True)
    stats = SyncStats()

    for inbox_root in inbox_roots:
        for candidate in iter_files(inbox_root):
            working_file = processing_root / working_name(candidate)

            if working_file.exists():
                if bytes_equal(candidate, working_file):
                    stats = stats.add(SyncStats(claim_skipped_unchanged=1))
                    continue
            elif processing_has_same_bytes(candidate, processing_root):
                stats = stats.add(SyncStats(claim_skipped_duplicate=1))
                continue

            shutil.copy2(candidate, working_file)
            stats = stats.add(SyncStats(claimed=1))

    return stats


def default_page_scanner_inbox(raw_data_root: Path) -> Path:
    workspace_root = raw_data_root.parent.parent
    return workspace_root / "Automation Personal" / "Page Scanner" / "data" / "inbox"


def run(
    *,
    vault_root: Path | None = None,
    raw_data_root: Path | None = None,
    page_scanner_inbox: Path | None = None,
    obsidian_config: Path = DEFAULT_OBSIDIAN_CONFIG,
) -> SyncStats:
    root = configure_raw_data_root(raw_data_root)
    inbox_root = root / "inbox"
    processing_root = root / "processing"
    page_scanner_root = page_scanner_inbox or default_page_scanner_inbox(root)
    vault = vault_root.expanduser().resolve() if vault_root else discover_vault_path(obsidian_config)

    mirror_stats = mirror_vault_to_inbox(vault, inbox_root)
    claim_stats = claim_candidates([inbox_root, page_scanner_root], processing_root)
    return mirror_stats.add(claim_stats)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Mirror Obsidian into Raw Data/inbox and claim feeder files into processing."
    )
    parser.add_argument("--vault", type=Path, help="Override the discovered Obsidian vault path.")
    parser.add_argument(
        "--raw-data-root",
        type=Path,
        help="Override RAW_DATA_ROOT; defaults to env var or this script's Raw Data root.",
    )
    parser.add_argument(
        "--page-scanner-inbox",
        type=Path,
        help="Override Automation Personal/Page Scanner/data/inbox.",
    )
    parser.add_argument(
        "--obsidian-config",
        type=Path,
        default=DEFAULT_OBSIDIAN_CONFIG,
        help="Path to Obsidian's obsidian.json.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    stats = run(
        vault_root=args.vault,
        raw_data_root=args.raw_data_root,
        page_scanner_inbox=args.page_scanner_inbox,
        obsidian_config=args.obsidian_config,
    )
    print(
        "mirror copied={mirrored} skipped={mirror_skipped}; "
        "claim copied={claimed} skipped_unchanged={claim_skipped_unchanged} "
        "skipped_duplicate={claim_skipped_duplicate}".format(**stats.__dict__)
    )


if __name__ == "__main__":
    main()
