from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
import hashlib
from pathlib import Path
import shutil
from typing import Literal

from ingestion.intake.base import Extractor, IntakeResult
from ingestion.intake.extractors import (
    ImageExtractor,
    LegacyWordExtractor,
    MarkdownPassthroughExtractor,
    PdfExtractor,
    WordExtractor,
)


class UnroutableFileError(ValueError):
    pass


class DownstreamUnavailableError(RuntimeError):
    pass


VaultWriter = Callable[[Path, IntakeResult], Path | str | None]
PendingApprovalStager = Callable[[Path, IntakeResult], int | str | None]
PostPublishMover = Callable[[Path, IntakeResult], Path]
CONTROL_FILENAMES = {".book.json", "book.txt"}


@dataclass(frozen=True)
class FunnelFileResult:
    source_path: Path
    title: str
    status: Literal["published", "awaiting_approval"]
    destination: Path | None = None
    handoff_id: int | str | None = None


@dataclass(frozen=True)
class FunnelRunReport:
    files: tuple[FunnelFileResult, ...]

    @property
    def published_count(self) -> int:
        return sum(item.status == "published" for item in self.files)

    @property
    def awaiting_approval_count(self) -> int:
        return sum(item.status == "awaiting_approval" for item in self.files)


@dataclass(frozen=True)
class PreparedFile:
    """One routed and extracted file, before any durable side effect."""

    source_path: Path
    extractor: Extractor
    result: IntakeResult
    content_hash: str


def default_extractors() -> tuple[Extractor, ...]:
    """Extractors owned by Component 1.

    Image OCR is available on macOS when Component 2's runtime dependencies
    are installed. Legacy .doc extraction shells out to macOS's built-in
    textutil to convert to .docx first; it requires no extra install but is
    macOS-only, matching the rest of this pipeline. It is not full-fidelity:
    textutil's .doc conversion flattens tables and drops heading styles, so
    a .doc containing a table is routed to approval instead of silently
    losing structure -- see LegacyWordExtractor's docstring.
    """

    return (
        ImageExtractor(),
        PdfExtractor(),
        WordExtractor(),
        LegacyWordExtractor(),
        MarkdownPassthroughExtractor(),
    )


def scan_drop_folder(drop_folder: Path) -> list[Path]:
    if not drop_folder.is_dir():
        raise NotADirectoryError(drop_folder)
    return sorted(
        (
            path
            for path in drop_folder.iterdir()
            if path.is_file() and path.name not in CONTROL_FILENAMES
        ),
        key=lambda path: (path.name.casefold(), path.name),
    )


def route_file(path: Path, extractors: Sequence[Extractor]) -> Extractor:
    matches = [extractor for extractor in extractors if extractor.handles(path)]
    if not matches:
        raise UnroutableFileError(f"no intake extractor handles {path.name!r}")
    if len(matches) > 1:
        names = ", ".join(type(extractor).__name__ for extractor in matches)
        raise UnroutableFileError(
            f"multiple intake extractors handle {path.name!r}: {names}"
        )
    return matches[0]


def _processed_destination(source: Path, processed_folder: Path) -> Path:
    destination = processed_folder / source.name
    if not destination.exists():
        return destination

    counter = 2
    while True:
        candidate = processed_folder / f"{source.stem}-{counter}{source.suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def prepare_file(path: Path, extractors: Sequence[Extractor]) -> PreparedFile:
    """Route and extract one file without publishing, parking, or moving it."""

    source = Path(path)
    extractor = route_file(source, extractors)
    content_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    return PreparedFile(
        source_path=source,
        extractor=extractor,
        result=extractor.extract(source),
        content_hash=content_hash,
    )


def publish_prepared(
    vault: Path,
    prepared: PreparedFile,
    *,
    write_note_to_vault: VaultWriter,
) -> Path:
    """Write one prepared result to the vault without moving its source."""

    published = write_note_to_vault(vault, prepared.result)
    if published is None:
        raise DownstreamUnavailableError(
            f"vault writer returned no path for {prepared.source_path.name!r}"
        )
    return Path(published)


def move_published_source(
    prepared: PreparedFile,
    *,
    drop_folder: Path,
    post_publish_destination: Mapping[type[Extractor], PostPublishMover] | None = None,
) -> Path:
    """Move a successfully published source to its configured destination."""

    source = prepared.source_path
    destination_mapper = (post_publish_destination or {}).get(type(prepared.extractor))
    if destination_mapper is None:
        processed_folder = Path(drop_folder) / "processed"
        processed_folder.mkdir(parents=True, exist_ok=True)
        destination = _processed_destination(source, processed_folder)
    else:
        destination = Path(destination_mapper(source, prepared.result))
        destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), destination)
    return destination


def run_funnel(
    drop_folder: Path,
    vault: Path,
    *,
    extractors: Sequence[Extractor] | None = None,
    write_note_to_vault: VaultWriter | None = None,
    park_for_review: PendingApprovalStager | None = None,
    post_publish_destination: Mapping[type[Extractor], PostPublishMover] | None = None,
) -> FunnelRunReport:
    """Run one synchronous pass over a drop folder.

    The two callbacks are the explicit Component 4 and Component 2 seams. A
    file is never moved unless its vault write succeeds, and an approval-bound
    file is never written to the vault or moved.
    """

    candidates = scan_drop_folder(drop_folder)
    active_extractors = (
        tuple(extractors) if extractors is not None else default_extractors()
    )
    results: list[FunnelFileResult] = []

    for source in candidates:
        prepared = prepare_file(source, active_extractors)
        result = prepared.result
        if result.needs_approval:
            if park_for_review is None:
                raise DownstreamUnavailableError(
                    f"{source.name!r} requires approval but no pending-review "
                    "stager was supplied"
                )
            handoff_id = park_for_review(source, result)
            results.append(
                FunnelFileResult(
                    source_path=source,
                    title=result.title,
                    status="awaiting_approval",
                    handoff_id=handoff_id,
                )
            )
            continue

        if write_note_to_vault is None:
            raise DownstreamUnavailableError(
                f"{source.name!r} is approved but Component 4's vault writer "
                "was not supplied"
            )
        published_path = publish_prepared(
            vault,
            prepared,
            write_note_to_vault=write_note_to_vault,
        )
        move_published_source(
            prepared,
            drop_folder=drop_folder,
            post_publish_destination=post_publish_destination,
        )
        results.append(
            FunnelFileResult(
                source_path=source,
                title=result.title,
                status="published",
                destination=(
                    published_path
                ),
            )
        )

    return FunnelRunReport(files=tuple(results))
