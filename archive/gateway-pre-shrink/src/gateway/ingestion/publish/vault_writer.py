"""Write intake results to Obsidian and archive approved scanner photos."""

from __future__ import annotations

from pathlib import Path
import json
import re
import shutil
from typing import Any, NamedTuple

from gateway.ingestion.config import central_database_root
from gateway.ingestion.intake.base import IntakeResult
from gateway.ingestion.sources import book_metadata
from gateway.ingestion.sources.page_scanner import store


PAGE_SCANNERS_FOLDER = "Page Scanners"

# T63: a book's highlighted passages are accumulated here, one document per
# book, as each photo is approved -- rather than each page note being handed
# whole to the segmentation model. `sources/obsidian.py::capture_book_highlights()`
# reads this back and captures each page as a parent with explicit passage spans.
HIGHLIGHTS_DOC_HEADER_MARKER = "<!-- page_scanner_highlights_doc -->"
_PAGE_MARKER_RE = re.compile(r"^<!-- page_scanner_id: (\d+) -->$")
_PASSAGE_MARKER_RE = re.compile(r"^<!-- page_scanner_passage: (\d+) -->$")
_PASSAGE_END_RE = re.compile(r"^<!-- /page_scanner_passage: (\d+) -->$")


class ApprovalRequiredError(RuntimeError):
    """Raised when approval-bound content bypasses the approval wrapper."""


def _available_destination(destination: Path) -> Path:
    if not destination.exists():
        return destination
    counter = 2
    while True:
        candidate = destination.with_name(
            f"{destination.stem}-{counter}{destination.suffix}"
        )
        if not candidate.exists():
            return candidate
        counter += 1


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _resolved_book(result: IntakeResult) -> tuple[dict[str, Any], str, str]:
    metadata = _mapping(result.frontmatter.get("book_meta"))
    title = str(metadata.get("title") or "").strip()
    if not title:
        raise ValueError("Page Scanner publication requires a resolved book title")
    return metadata, title, book_metadata.slugify_title(title)


def _is_page_scanner_result(result: IntakeResult) -> bool:
    return isinstance(result.frontmatter.get("page_scanner"), dict)


def _safe_note_stem(title: str) -> str:
    stem = title.strip()
    if stem.lower().endswith(".md"):
        stem = stem[:-3].rstrip()
    if not stem or stem in {".", ".."} or Path(stem).name != stem:
        raise ValueError(f"invalid vault note title: {title!r}")
    return stem


def _quote_passage(text: str) -> list[str]:
    return [f"> {line}" if line else ">" for line in text.splitlines()]


def _render_page_scanner_note(result: IntakeResult) -> str:
    metadata, book_title, _slug = _resolved_book(result)
    scanner = _mapping(result.frontmatter.get("page_scanner"))
    passages_value = scanner.get("passages")
    passages = passages_value if isinstance(passages_value, list) else []
    source_photo = str(scanner.get("source_photo") or "")
    author = str(metadata.get("author") or scanner.get("author") or "")
    page_number = scanner.get("page_number")
    page_id = scanner.get("page_scanner_id")
    if page_id is None:
        raise ValueError("Page Scanner publication requires page_scanner_id")

    lines = [
        f"# {book_title}",
        "",
        f"source_photo: {source_photo}",
        f"book_title: {book_title}",
        f"book_author: {author}",
        f"page_number: {page_number if page_number is not None else ''}",
        "quality_signals: "
        f"blur={scanner.get('blur_score') if scanner.get('blur_score') is not None else ''} "
        f"glare={scanner.get('glare_score') if scanner.get('glare_score') is not None else ''} "
        f"conf={scanner.get('conf_ratio') if scanner.get('conf_ratio') is not None else ''}",
        f"page_scanner_id: {page_id}",
        "",
    ]

    passage_texts: list[str] = []
    for passage in passages:
        if isinstance(passage, dict):
            text = str(passage.get("edited_text") or passage.get("text") or "").strip()
            if text:
                passage_texts.append(text)
    if not passage_texts and result.markdown_text.strip():
        passage_texts = [result.markdown_text.strip()]
    for text in passage_texts:
        lines.extend(_quote_passage(text))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _highlights_doc_path(vault: Path, slug: str) -> Path:
    return Path(vault) / PAGE_SCANNERS_FOLDER / slug / f"{slug}-highlights.md"


def is_book_highlights_doc(text: str) -> bool:
    lines = text.splitlines()
    return bool(lines) and lines[0].strip() == HIGHLIGHTS_DOC_HEADER_MARKER


def _unquote_passage(lines: list[str]) -> str:
    return "\n".join(line[2:] if line.startswith("> ") else "" for line in lines)


def append_book_highlight_passages(vault: Path, result: IntakeResult) -> Path:
    """Append one approved photo's marked passages to its book's shared
    highlights document in the vault, at `Page Scanners/<slug>/<slug>-highlights.md`.

    T63's settled direction: a photo's highlighted passages become highlights
    by first accumulating into one document per book here, as each photo is
    approved, which `sources/obsidian.py::capture_book_highlights()` later
    reads to capture one page parent with one explicit span per passage --
    instead of handing the whole page note to the segmentation model.

    Safe to call more than once for the same page: guarded by the page's
    `page_scanner_id` marker, so a retried publish cannot duplicate a page's
    passages in the document.
    """
    metadata, book_title, slug = _resolved_book(result)
    scanner = _mapping(result.frontmatter.get("page_scanner"))
    page_id = scanner.get("page_scanner_id")
    if page_id is None:
        raise ValueError("Page Scanner publication requires page_scanner_id")
    page_number = scanner.get("page_number")
    passages_value = scanner.get("passages")
    passages = passages_value if isinstance(passages_value, list) else []
    passage_texts = [
        (
            int(passage["id"] if passage.get("id") is not None else index),
            str(passage.get("edited_text") or passage.get("text") or "").strip(),
        )
        for index, passage in enumerate(passages)
        if isinstance(passage, dict)
    ]
    passage_texts = [(passage_id, text) for passage_id, text in passage_texts if text]

    doc_path = _highlights_doc_path(vault, slug)
    page_marker = f"<!-- page_scanner_id: {page_id} -->"
    if doc_path.exists() and page_marker in doc_path.read_text(encoding="utf-8"):
        return doc_path
    if not passage_texts:
        return doc_path

    lines: list[str] = []
    if not doc_path.exists():
        lines.append(HIGHLIGHTS_DOC_HEADER_MARKER)
        lines.append(f"# {book_title} — highlights")
        lines.append("")
    lines.append(page_marker)
    lines.append(f"## p{page_number if page_number is not None else page_id}")
    lines.append("")
    for passage_id, text in passage_texts:
        # Machine markers sit outside the selected text.  The raw passage is
        # therefore an exact contiguous slice of this vault document, even
        # when it spans several lines.
        lines.append(f"<!-- page_scanner_passage: {passage_id} -->")
        lines.extend(text.splitlines())
        lines.append(f"<!-- /page_scanner_passage: {passage_id} -->")
        lines.append("")
    block = "\n".join(lines).rstrip("\n") + "\n\n"
    doc_path.parent.mkdir(parents=True, exist_ok=True)
    with doc_path.open("a", encoding="utf-8") as handle:
        handle.write(block)
    return doc_path


class BookHighlightPassage(NamedTuple):
    """One marked passage read back out of a book highlights document."""

    page_scanner_id: int
    passage_id: int
    passage_index: int
    text: str
    parent_start_char: int
    parent_end_char: int


def iter_book_highlight_passages(doc_path: Path) -> list[BookHighlightPassage]:
    """Parse a book highlights document into its individual marked passages,
    in the order they were appended.

    Not every `.md` file under a book's vault folder is this document --
    only one written by `append_book_highlight_passages()`, identified by
    `HIGHLIGHTS_DOC_HEADER_MARKER` on its first line. Passages are returned
    with their character offsets in the document, for `UserSelection`
    provenance -- the offsets describe where the passage sits in *this*
    document, which is what a passage was actually selected from.
    """
    full_text = doc_path.read_text(encoding="utf-8")
    if not is_book_highlights_doc(full_text):
        return []

    passages: list[BookHighlightPassage] = []
    current_page: int | None = None
    passage_index = 0
    passage_id: int | None = None
    explicit_passage = False
    block: list[str] = []
    block_start: int | None = None
    pos = 0

    def flush(end: int) -> None:
        nonlocal block, passage_index, passage_id, block_start, explicit_passage
        if block and current_page is not None and block_start is not None:
            if explicit_passage:
                raw = full_text[block_start:end]
                text = raw.rstrip("\n")
                selection_end = block_start + len(text)
            else:
                text = _unquote_passage(block)
                selection_end = end
            passages.append(
                BookHighlightPassage(
                    current_page,
                    passage_id if passage_id is not None else passage_index,
                    passage_index,
                    text,
                    block_start,
                    selection_end,
                )
            )
            passage_index += 1
        block = []
        block_start = None
        passage_id = None
        explicit_passage = False

    for line in full_text.splitlines(keepends=True):
        stripped = line.rstrip("\n")
        marker = _PAGE_MARKER_RE.match(stripped.strip())
        passage_marker = _PASSAGE_MARKER_RE.match(stripped.strip())
        passage_end = _PASSAGE_END_RE.match(stripped.strip())
        if marker:
            flush(pos)
            current_page = int(marker.group(1))
            passage_index = 0
        elif passage_marker:
            flush(pos)
            passage_id = int(passage_marker.group(1))
            explicit_passage = True
            block_start = pos + len(line)
        elif passage_end:
            if not explicit_passage or passage_id != int(passage_end.group(1)):
                raise ValueError(f"mismatched passage marker in {doc_path}")
            flush(pos)
        elif explicit_passage:
            block.append(stripped)
        elif stripped.startswith(">"):
            if block_start is None:
                block_start = pos
            block.append(stripped)
        else:
            flush(pos)
        pos += len(line)
    if explicit_passage:
        raise ValueError(f"unclosed passage marker in {doc_path}")
    flush(pos)
    return passages


def _write_new_note(folder: Path, stem: str, content: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    counter = 1
    while True:
        suffix = "" if counter == 1 else f"-{counter}"
        destination = folder / f"{stem}{suffix}.md"
        try:
            with destination.open("x", encoding="utf-8") as handle:
                handle.write(content)
            return destination
        except FileExistsError:
            counter += 1


def write_note_to_vault(vault: Path, result: IntakeResult) -> Path:
    """Write one approved intake result without overwriting an existing note."""

    if result.needs_approval:
        raise ApprovalRequiredError(
            "approval-bound content must be published through publish_approved_page"
        )
    resolved_vault = Path(vault).expanduser()
    if resolved_vault.exists() and not resolved_vault.is_dir():
        raise NotADirectoryError(resolved_vault)

    stem = _safe_note_stem(result.title)
    if _is_page_scanner_result(result):
        _metadata, _title, slug = _resolved_book(result)
        folder = resolved_vault / PAGE_SCANNERS_FOLDER / slug
        content = _render_page_scanner_note(result)
    else:
        folder = resolved_vault
        content = result.markdown_text
    return _write_new_note(folder, stem, content)


def page_scanner_photo_destination(
    source: Path,
    result: IntakeResult,
    *,
    database_root: Path | None = None,
) -> Path:
    """Resolve the durable destination used by direct and funnel publication."""

    _metadata, _title, slug = _resolved_book(result)
    source = Path(source)
    if source.parent.name != slug:
        raise ValueError(
            "resolved book slug does not match the finalized photo folder: "
            f"{slug!r} != {source.parent.name!r}"
        )
    root = Path(database_root) if database_root is not None else central_database_root(source)
    folder = root / "page_scanner_photos" / slug
    return _available_destination(folder / source.name)


def _page_metadata(page: dict[str, Any]) -> dict[str, Any]:
    value = page.get("book_meta")
    if not value:
        return {}
    decoded = json.loads(str(value))
    if not isinstance(decoded, dict):
        raise ValueError("page book_meta must decode to an object")
    return decoded


def _approved_result(
    page: dict[str, Any],
    passages: list[dict[str, Any]],
    result: IntakeResult,
    photo_destination: Path,
) -> IntakeResult:
    metadata = _page_metadata(page) or _mapping(result.frontmatter.get("book_meta"))
    title = str(metadata.get("title") or "").strip()
    if not title:
        raise ValueError("Page Scanner publication requires a resolved book title")
    slug = book_metadata.slugify_title(title)
    page_number = page.get("page_number")
    note_title = (
        f"{slug}-p{page_number}"
        if page_number is not None
        else f"{slug}-page-{page['id']}"
    )
    scanner = {
        **_mapping(result.frontmatter.get("page_scanner")),
        "source_photo": str(photo_destination),
        "author": page.get("author"),
        "page_number": page_number,
        "page_scanner_id": page["id"],
        "blur_score": page.get("blur_score"),
        "glare_score": page.get("glare_score"),
        "conf_ratio": page.get("conf_ratio"),
        "passages": [
            {
                "id": passage.get("id"),
                "text": passage.get("ocr_text") or "",
                "edited_text": passage.get("edited_text"),
            }
            for passage in passages
        ],
    }
    markdown_text = "\n\n".join(
        str(passage.get("edited_text") or passage.get("ocr_text") or "").strip()
        for passage in passages
        if str(passage.get("edited_text") or passage.get("ocr_text") or "").strip()
    )
    return result.model_copy(
        update={
            "title": note_title,
            "markdown_text": markdown_text,
            "needs_approval": False,
            "approval_reason": None,
            "frontmatter": {
                **result.frontmatter,
                "book_meta": metadata,
                "page_scanner": scanner,
            },
        }
    )


def approved_intake_result(
    db_path: Path,
    page_id: int,
    result: IntakeResult,
    *,
    photo_destination: Path | None = None,
) -> IntakeResult:
    """Materialize a reviewed store row as an approved, publishable result."""

    page = store.get_page(db_path, page_id)
    if page is None:
        raise ValueError(f"page {page_id} not found")
    if page.get("status") != "reviewed":
        raise ApprovalRequiredError(
            f"page {page_id} must have status 'reviewed' before publication"
        )
    passages = store.get_passages(db_path, page_id)
    if _is_page_scanner_result(result):
        if photo_destination is None:
            raise ValueError("photo_destination is required for a scanner result")
        return _approved_result(page, passages, result, photo_destination)
    markdown_text = "\n\n".join(
        str(passage.get("edited_text") or passage.get("ocr_text") or "").strip()
        for passage in passages
        if str(passage.get("edited_text") or passage.get("ocr_text") or "").strip()
    )
    return result.model_copy(
        update={
            "markdown_text": markdown_text,
            "needs_approval": False,
            "approval_reason": None,
        }
    )


def finalize_published_page(
    db_path: Path, page_id: int, *, moved_to: Path | None = None
) -> None:
    """Stamp a reviewed page after the coordinator has durably moved it."""

    if moved_to is not None:
        store.set_image_path(db_path, page_id, str(moved_to))
    store.update_page_status(db_path, page_id, "published")


def publish_approved_page(
    vault: Path,
    db_path: Path,
    page_id: int,
    result: IntakeResult,
) -> Path:
    """Publish one cockpit-approved page, then durably archive its photo."""

    page = store.get_page(db_path, page_id)
    if page is None:
        raise ValueError(f"page {page_id} not found")
    if page.get("status") != "reviewed":
        raise ApprovalRequiredError(
            f"page {page_id} must have status 'reviewed' before publication"
        )
    source = Path(str(page.get("image_path") or ""))
    if not source.is_file():
        raise FileNotFoundError(source)

    preliminary = result.model_copy(
        update={"frontmatter": {**result.frontmatter, "book_meta": _page_metadata(page)}}
    )
    photo_destination = page_scanner_photo_destination(source, preliminary)
    approved = _approved_result(
        page, store.get_passages(db_path, page_id), result, photo_destination
    )

    note_path = write_note_to_vault(vault, approved)
    photo_destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), photo_destination)
    old_status = str(page.get("status") or "")
    image_path_updated = False
    status_updated = False
    try:
        store.set_image_path(db_path, page_id, str(photo_destination))
        image_path_updated = True
        store.update_page_status(db_path, page_id, "published")
        status_updated = True
    except Exception:
        rollback_errors: list[Exception] = []
        current: dict[str, Any] | None = None
        try:
            current = store.get_page(db_path, page_id)
        except Exception as error:
            rollback_errors.append(error)
        if image_path_updated or (
            current is not None and current.get("image_path") != str(source)
        ):
            try:
                store.set_image_path(db_path, page_id, str(source))
            except Exception as error:
                rollback_errors.append(error)
        if status_updated or (
            current is not None and current.get("status") != old_status
        ):
            try:
                store.update_page_status(db_path, page_id, old_status)
            except Exception as error:
                rollback_errors.append(error)
        try:
            shutil.move(str(photo_destination), source)
        except Exception as error:
            rollback_errors.append(error)
        if rollback_errors:
            raise RuntimeError(
                "photo archival database update failed and rollback was incomplete"
            ) from rollback_errors[0]
        raise
    return note_path
