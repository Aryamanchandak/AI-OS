from __future__ import annotations

import json
from pathlib import Path

import pytest

from ingestion.intake.base import IntakeResult
from ingestion.publish import vault_writer
from ingestion.publish.vault_writer import (
    ApprovalRequiredError,
    append_book_highlight_passages,
    approved_intake_result,
    is_book_highlights_doc,
    iter_book_highlight_passages,
    publish_approved_page,
    write_note_to_vault,
)
from ingestion.sources.page_scanner import store


def _result(*, needs_approval: bool = True) -> IntakeResult:
    return IntakeResult(
        markdown_text="stale extractor text",
        title="IMG_4821",
        needs_approval=needs_approval,
        approval_reason="photo OCR requires approval" if needs_approval else None,
        frontmatter={
            "book_meta": {"title": "Atomic Habits", "author": "James Clear"},
            "page_scanner": {},
        },
    )


def _reviewed_page(tmp_path: Path, *, page_number: int | None = None) -> tuple[Path, int, Path]:
    db_path = tmp_path / "scanner.db"
    capture_folder = tmp_path / "capture" / "atomic-habits"
    capture_folder.mkdir(parents=True)
    photo = capture_folder / "IMG_4821.jpg"
    photo.write_bytes(b"photo")
    store.init_db(db_path)
    page_id = store.insert_page(
        db_path,
        batch="camera batch",
        author="Fallback Author",
        image_path=str(photo),
        file_hash="hash",
        status="reviewed",
        page_number=page_number,
        blur_score=123.5,
        glare_score=0.02,
        conf_ratio=0.91,
        book_meta=json.dumps({"title": "Atomic Habits", "author": "James Clear"}),
    )
    assert page_id is not None
    store.insert_passage(
        db_path,
        page_id,
        bbox=[1, 2, 3, 4],
        ocr_text="uncorrected text",
        edited_text="Corrected first passage.",
    )
    store.insert_passage(
        db_path,
        page_id,
        bbox=[5, 6, 7, 8],
        ocr_text="Second OCR passage.",
        edited_text="",
    )
    return db_path, page_id, photo


def test_write_note_rejects_content_still_waiting_for_approval(tmp_path: Path) -> None:
    with pytest.raises(ApprovalRequiredError):
        write_note_to_vault(tmp_path / "vault", _result())
    assert not (tmp_path / "vault").exists()


def test_write_note_preserves_generic_extractor_markdown(tmp_path: Path) -> None:
    result = IntakeResult(
        markdown_text="# Existing title\n\nExact pass-through body.\n",
        title="Imported note",
        needs_approval=False,
    )

    note = write_note_to_vault(tmp_path / "vault", result)

    assert note == tmp_path / "vault" / "Imported note.md"
    assert note.read_text(encoding="utf-8") == result.markdown_text


def test_publish_approved_page_writes_metadata_moves_photo_and_suffixes_collision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path, page_id, photo = _reviewed_page(tmp_path, page_number=42)
    database_root = tmp_path / "Database"
    monkeypatch.setattr(
        vault_writer, "central_database_root", lambda _start: database_root
    )
    vault = tmp_path / "vault"
    existing = vault / "Page Scanners" / "atomic-habits" / "atomic-habits-p42.md"
    existing.parent.mkdir(parents=True)
    existing.write_text("existing", encoding="utf-8")

    note = publish_approved_page(vault, db_path, page_id, _result())

    assert note.name == "atomic-habits-p42-2.md"
    text = note.read_text(encoding="utf-8")
    archived = database_root / "page_scanner_photos" / "atomic-habits" / photo.name
    assert text == (
        "# Atomic Habits\n\n"
        f"source_photo: {archived}\n"
        "book_title: Atomic Habits\n"
        "book_author: James Clear\n"
        "page_number: 42\n"
        "quality_signals: blur=123.5 glare=0.02 conf=0.91\n"
        f"page_scanner_id: {page_id}\n\n"
        "> Corrected first passage.\n\n"
        "> Second OCR passage.\n"
    )
    assert archived.read_bytes() == b"photo"
    assert not photo.exists()
    page = store.get_page(db_path, page_id)
    assert page is not None
    assert page["status"] == "published"
    assert page["image_path"] == str(archived)


def test_publish_uses_page_id_title_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path, page_id, _photo = _reviewed_page(tmp_path)
    monkeypatch.setattr(
        vault_writer, "central_database_root", lambda _start: tmp_path / "Database"
    )
    note = publish_approved_page(tmp_path / "vault", db_path, page_id, _result())
    assert note.name == f"atomic-habits-page-{page_id}.md"


def test_failed_vault_write_leaves_photo_and_database_untouched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path, page_id, photo = _reviewed_page(tmp_path)
    monkeypatch.setattr(
        vault_writer, "central_database_root", lambda _start: tmp_path / "Database"
    )
    monkeypatch.setattr(
        vault_writer, "write_note_to_vault", lambda *_args: (_ for _ in ()).throw(RuntimeError("no vault"))
    )

    with pytest.raises(RuntimeError, match="no vault"):
        publish_approved_page(tmp_path / "vault", db_path, page_id, _result())
    assert photo.exists()
    page = store.get_page(db_path, page_id)
    assert page is not None
    assert page["status"] == "reviewed"
    assert page["image_path"] == str(photo)


@pytest.mark.parametrize("failing_operation", ["set_image_path", "update_page_status"])
def test_database_failure_rolls_photo_and_row_back(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failing_operation: str,
) -> None:
    db_path, page_id, photo = _reviewed_page(tmp_path)
    database_root = tmp_path / "Database"
    monkeypatch.setattr(
        vault_writer, "central_database_root", lambda _start: database_root
    )
    monkeypatch.setattr(
        vault_writer.store,
        failing_operation,
        lambda *_args: (_ for _ in ()).throw(RuntimeError("database failed")),
    )

    with pytest.raises(RuntimeError, match="database failed"):
        publish_approved_page(tmp_path / "vault", db_path, page_id, _result())
    archived = database_root / "page_scanner_photos" / "atomic-habits" / photo.name
    assert photo.exists()
    assert not archived.exists()
    page = store.get_page(db_path, page_id)
    assert page is not None
    assert page["status"] == "reviewed"
    assert page["image_path"] == str(photo)


def test_append_book_highlight_passages_writes_marker_and_passages(tmp_path: Path) -> None:
    db_path, page_id, photo = _reviewed_page(tmp_path, page_number=42)
    approved = approved_intake_result(
        db_path, page_id, _result(), photo_destination=tmp_path / "archive" / photo.name
    )

    doc_path = append_book_highlight_passages(tmp_path / "vault", approved)

    assert doc_path == (
        tmp_path / "vault" / "Page Scanners" / "atomic-habits" / "atomic-habits-highlights.md"
    )
    text = doc_path.read_text(encoding="utf-8")
    assert is_book_highlights_doc(text)
    assert f"<!-- page_scanner_id: {page_id} -->" in text
    assert "Corrected first passage." in text
    assert "Second OCR passage." in text


def test_append_book_highlight_passages_is_idempotent_on_retry(tmp_path: Path) -> None:
    """A retried publish must not duplicate a page's passages in the document."""
    db_path, page_id, photo = _reviewed_page(tmp_path, page_number=42)
    approved = approved_intake_result(
        db_path, page_id, _result(), photo_destination=tmp_path / "archive" / photo.name
    )

    first = append_book_highlight_passages(tmp_path / "vault", approved)
    before = first.read_text(encoding="utf-8")
    second = append_book_highlight_passages(tmp_path / "vault", approved)

    assert second == first
    assert second.read_text(encoding="utf-8") == before


def test_iter_book_highlight_passages_round_trips_multiple_pages(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    db_path, page_id_one, _photo_one = _reviewed_page(tmp_path, page_number=42)
    approved_one = approved_intake_result(
        db_path, page_id_one, _result(), photo_destination=tmp_path / "archive" / "p42.jpg"
    )
    append_book_highlight_passages(vault, approved_one)

    # A second page of the same book, appended afterwards.
    page_id_two = store.insert_page(
        db_path,
        batch="camera batch",
        author="Fallback Author",
        image_path=str(tmp_path / "capture" / "atomic-habits" / "IMG_two.jpg"),
        file_hash="hash-two",
        status="reviewed",
        page_number=43,
        blur_score=1.0,
        glare_score=0.0,
        conf_ratio=0.9,
        book_meta=json.dumps({"title": "Atomic Habits", "author": "James Clear"}),
    )
    assert page_id_two is not None
    store.insert_passage(
        db_path, page_id_two, bbox=[0, 0, 1, 1], ocr_text="Third passage.", edited_text=""
    )
    approved_two = approved_intake_result(
        db_path, page_id_two, _result(), photo_destination=tmp_path / "archive" / "p43.jpg"
    )
    doc_path = append_book_highlight_passages(vault, approved_two)

    passages = iter_book_highlight_passages(doc_path)

    assert [passage.text for passage in passages] == [
        "Corrected first passage.",
        "Second OCR passage.",
        "Third passage.",
    ]
    assert [passage.page_scanner_id for passage in passages] == [
        page_id_one,
        page_id_one,
        page_id_two,
    ]
    assert [passage.passage_index for passage in passages] == [0, 1, 0]

    full_text = doc_path.read_text(encoding="utf-8")
    for passage in passages:
        sliced = full_text[passage.parent_start_char : passage.parent_end_char]
        assert sliced == passage.text


def test_iter_book_highlight_passages_rejects_a_non_highlights_note(tmp_path: Path) -> None:
    note = tmp_path / "ordinary.md"
    note.write_text("# Just a note\n\n> Not a highlights document.\n", encoding="utf-8")

    assert iter_book_highlight_passages(note) == []
    assert not is_book_highlights_doc(note.read_text(encoding="utf-8"))
