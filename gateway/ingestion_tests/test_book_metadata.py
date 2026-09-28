from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PIL import Image
import pytest

from gateway.ingestion.sources import book_metadata
from gateway.ingestion.sources.page_scanner import store


def _metadata(
    title: str = "Atomic Habits",
    *,
    confidence: str = "exact",
    confirmed: bool | None = None,
) -> dict[str, Any]:
    value: dict[str, Any] = {
        "title": title,
        "author": "James Clear",
        "year": 2018,
        "isbn": "9780735211292",
        "subjects": ["Habit"],
        "cover_url": None,
        "meta_source": "openlibrary",
        "confidence": confidence,
        "query": title,
    }
    if confirmed is not None:
        value["confirmed"] = confirmed
    return value


def _write_cache(folder: Path, metadata: dict[str, Any]) -> None:
    (folder / book_metadata.CACHE_NAME).write_text(
        json.dumps(metadata), encoding="utf-8"
    )


def test_resolve_book_uses_google_fallback_and_never_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def no_openlibrary(query: str) -> None:
        calls.append(f"open:{query}")
        return None

    def google(query: str) -> dict[str, Any]:
        calls.append(f"google:{query}")
        return _metadata("Atomic Habits")

    monkeypatch.setattr(book_metadata, "_from_openlibrary", no_openlibrary)
    monkeypatch.setattr(book_metadata, "_from_google_books", google)
    assert book_metadata.resolve_book("Atomic Habits")["title"] == "Atomic Habits"
    assert calls == ["open:Atomic Habits", "google:Atomic Habits"]

    monkeypatch.setattr(book_metadata, "_from_google_books", lambda _query: None)
    assert book_metadata.resolve_book("Unknown Book") == book_metadata._blank(
        "Unknown Book"
    )


@pytest.mark.parametrize(
    ("query", "title", "expected"),
    [
        ("Atomic Habits, James Clear", "Atomic Habits", "exact"),
        ("Atomic Routines and Habits", "Atomic Habits", "fuzzy"),
        ("Unrelated Query", "Atomic Habits", "low"),
        ("Anything", None, "none"),
    ],
)
def test_confidence_scoring(
    query: str, title: str | None, expected: str
) -> None:
    assert book_metadata._confidence(query, title) == expected


def test_load_or_resolve_uses_normalized_folder_name_and_cache_always_wins(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = tmp_path / "this-is-not-a-book-title"
    folder.mkdir()

    queries: list[str] = []

    def resolve(query: str) -> dict[str, Any]:
        queries.append(query)
        return _metadata(query, confidence="none")

    monkeypatch.setattr(book_metadata, "resolve_book", resolve)
    missing = book_metadata.load_or_resolve(folder)
    assert queries == ["this is not a book title"]
    assert missing["title"] == "this is not a book title"
    assert (folder / book_metadata.CACHE_NAME).exists()

    cached = _metadata("Hand Edited Title", confidence="low", confirmed=True)
    _write_cache(folder, cached)
    assert book_metadata.load_or_resolve(folder) == cached


def test_book_txt_resolves_once_and_corrupt_cache_is_replaced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = tmp_path / "scan-1"
    folder.mkdir()
    (folder / book_metadata.QUERY_FILE).write_text(
        "\n Atomic Habits, James Clear \nignored\n", encoding="utf-8"
    )
    (folder / book_metadata.CACHE_NAME).write_text("{broken", encoding="utf-8")
    queries: list[str] = []

    def resolve(query: str) -> dict[str, Any]:
        queries.append(query)
        return _metadata()

    monkeypatch.setattr(book_metadata, "resolve_book", resolve)
    resolved = book_metadata.load_or_resolve(folder)
    assert queries == ["Atomic Habits, James Clear"]
    assert resolved["confirmed"] is True
    assert json.loads(
        (folder / book_metadata.CACHE_NAME).read_text(encoding="utf-8")
    ) == resolved

    assert book_metadata.load_or_resolve(folder) == resolved
    assert queries == ["Atomic Habits, James Clear"]


def test_classify_page_sends_base64_image_to_local_profile(tmp_path: Path) -> None:
    cover = tmp_path / "cover.jpg"
    cover.write_bytes(b"page-scanner-photo")
    calls: list[dict[str, Any]] = []

    class FakeClient:
        def chat(self, **kwargs: Any) -> dict[str, Any]:
            calls.append(kwargs)
            return {
                "parsed": {
                    "is_cover": True,
                    "title": "Atomic Habits",
                    "author": "James Clear",
                }
            }

    result = book_metadata._classify_page(cover, chat_client=FakeClient())

    assert result == book_metadata.CoverReadResult(
        is_cover=True, title="Atomic Habits", author="James Clear"
    )
    assert calls[0]["profile"] == "cover-classification-v1"
    assert set(calls[0]) == {"messages", "profile", "response_format"}
    content = calls[0]["messages"][0]["content"]
    assert content[0]["type"] == "text"
    assert content[1] == {
        "type": "image",
        "media_type": "image/jpeg",
        "data": "cGFnZS1zY2FubmVyLXBob3Rv",
    }
    assert calls[0]["response_format"] == {
        "type": "json_schema",
        "schema": book_metadata.CoverReadResult.model_json_schema(),
    }


def test_classify_page_degrades_closed_without_client_or_on_error(
    tmp_path: Path,
) -> None:
    cover = tmp_path / "cover.jpg"
    cover.write_bytes(b"photo")

    class FailedClient:
        def chat(self, **kwargs: Any) -> dict[str, Any]:
            del kwargs
            raise RuntimeError("gateway unavailable")

    closed = book_metadata.CoverReadResult(is_cover=False)
    assert book_metadata._classify_page(cover) == closed
    assert book_metadata._classify_page(cover, chat_client=FailedClient()) == closed


def test_find_cover_uses_exif_order_and_skips_retake(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = tmp_path / "scan"
    retake = folder / "_retake"
    retake.mkdir(parents=True)

    def photo(name: str, captured: str, *, parent: Path = folder) -> Path:
        path = parent / name
        exif = Image.Exif()
        exif[36867] = captured
        Image.new("RGB", (4, 4), "white").save(path, exif=exif)
        return path

    interior = photo("interior.jpg", "2026:08:06 10:00:00")
    cover = photo("cover.jpg", "2026:08:06 10:01:00")
    photo("bad-cover.jpg", "2026:08:06 09:59:00", parent=retake)
    seen: list[Path] = []

    def classify(path: Path, *, chat_client: Any = None) -> book_metadata.CoverReadResult:
        del chat_client
        seen.append(path)
        return book_metadata.CoverReadResult(
            is_cover=path == cover,
            title="Atomic Habits" if path == cover else None,
            author="James Clear" if path == cover else None,
        )

    monkeypatch.setattr(book_metadata, "_classify_page", classify)
    result = book_metadata.find_cover(folder, chat_client=object())

    assert seen == [interior, cover]
    assert result == book_metadata.CoverReadResult(
        is_cover=True, title="Atomic Habits", author="James Clear"
    )


def test_folder_name_wins_without_invoking_cover_classification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = tmp_path / "scan"
    folder.mkdir()
    monkeypatch.setattr(
        book_metadata,
        "find_cover",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("folder fallback must not classify a cover")
        ),
    )
    queries: list[str] = []

    def resolve(query: str) -> dict[str, Any]:
        queries.append(query)
        return _metadata()

    monkeypatch.setattr(book_metadata, "resolve_book", resolve)
    resolved = book_metadata.load_or_resolve(folder, chat_client=object())

    assert queries == ["scan"]
    assert resolved["confirmed"] is True
    assert json.loads(
        (folder / book_metadata.CACHE_NAME).read_text(encoding="utf-8")
    ) == resolved


def test_gate_status_covers_clear_and_confirmation_states(tmp_path: Path) -> None:
    exact = tmp_path / "exact"
    exact.mkdir()
    _write_cache(exact, _metadata(confirmed=False))
    assert book_metadata.gate_status(exact) == "clear"

    confirmed = tmp_path / "confirmed"
    confirmed.mkdir()
    _write_cache(
        confirmed, _metadata(confidence="low", confirmed=True)
    )
    assert book_metadata.gate_status(confirmed) == "clear"

    uncertain = tmp_path / "uncertain"
    uncertain.mkdir()
    _write_cache(
        uncertain, _metadata(confidence="fuzzy", confirmed=False)
    )
    assert book_metadata.gate_status(uncertain) == "needs_confirm"

    corrected = tmp_path / "corrected"
    corrected.mkdir()
    corrected_metadata = _metadata(confidence="exact", confirmed=False)
    corrected_metadata["confirmation_required"] = True
    _write_cache(corrected, corrected_metadata)
    assert book_metadata.gate_status(corrected) == "needs_confirm"


def test_record_correction_stores_complete_lookup_candidate_without_confirming(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = tmp_path / "wrong-title"
    folder.mkdir()
    _write_cache(folder, _metadata("Wrong Title", confidence="low"))
    looked_up = _metadata("Sapiens: A Brief History of Humankind")
    looked_up["cover_url"] = "https://covers.example/sapiens.jpg"
    monkeypatch.setattr(book_metadata, "resolve_book", lambda _query: looked_up)

    returned = book_metadata.record_correction(
        folder,
        title="Sapiens",
        author="Yuval Noah Harari",
        db_path=tmp_path / "processed.db",
    )

    assert returned == folder
    assert folder.is_dir()
    cached = json.loads((folder / book_metadata.CACHE_NAME).read_text())
    assert cached == {
        **looked_up,
        "confirmed": False,
        "confirmation_required": True,
    }
    assert book_metadata.gate_status(folder) == "needs_confirm"


def test_record_correction_keeps_typed_fallback_unknown_when_lookup_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = tmp_path / "offline-book"
    folder.mkdir()
    monkeypatch.setattr(
        book_metadata, "resolve_book", lambda query: book_metadata._blank(query)
    )

    book_metadata.record_correction(
        folder,
        title="A Human Title",
        author="A Human Author",
        db_path=tmp_path / "processed.db",
    )

    cached = json.loads((folder / book_metadata.CACHE_NAME).read_text())
    assert cached["title"] == "A Human Title"
    assert cached["author"] == "A Human Author"
    assert cached["year"] is None
    assert cached["cover_url"] is None
    assert cached["meta_source"] == "human_fallback"
    assert cached["confirmation_required"] is True


def test_finalize_folder_rewrites_normal_and_retake_paths(tmp_path: Path) -> None:
    database = tmp_path / "processed.db"
    folder = tmp_path / "scan-1"
    retake = folder / "_retake"
    retake.mkdir(parents=True)
    first = folder / "page-1.jpg"
    second = retake / "page-2.jpg"
    first.touch()
    second.touch()
    _write_cache(folder, _metadata(confirmed=True))
    store.init_db(database)
    assert store.insert_page(
        database,
        batch="Book",
        author=None,
        image_path=str(first),
        file_hash="hash-1",
    ) is not None
    assert store.insert_page(
        database,
        batch="Book",
        author=None,
        image_path=str(second),
        file_hash="hash-2",
    ) is not None

    destination = book_metadata.finalize_resolved_folder(folder, db_path=database)

    assert destination == tmp_path / "atomic-habits"
    assert destination.is_dir()
    assert not folder.exists()
    assert [page["image_path"] for page in store.get_pages(database)] == [
        str(destination / "page-1.jpg"),
        str(destination / "_retake" / "page-2.jpg"),
    ]
    assert [page["file_hash"] for page in store.get_pages(database)] == [
        "hash-1",
        "hash-2",
    ]


def test_record_confirmation_persists_and_returns_renamed_folder(
    tmp_path: Path,
) -> None:
    database = tmp_path / "processed.db"
    folder = tmp_path / "scan-2"
    folder.mkdir()
    photo = folder / "page.jpg"
    photo.touch()
    _write_cache(
        folder, _metadata("Deep Work", confidence="low", confirmed=False)
    )
    store.init_db(database)
    assert store.insert_page(
        database,
        batch="Book",
        author=None,
        image_path=str(photo),
        file_hash="hash",
    ) is not None

    destination = book_metadata.record_confirmation(folder, db_path=database)

    assert destination == tmp_path / "deep-work"
    cached = json.loads(
        (destination / book_metadata.CACHE_NAME).read_text(encoding="utf-8")
    )
    assert cached["confirmed"] is True
    assert cached["confirmation_required"] is False
    assert store.get_pages(database)[0]["image_path"] == str(
        destination / "page.jpg"
    )


@pytest.mark.parametrize("suffix", [".gif", ".heic", ""])
def test_image_content_block_rejects_unsupported_types(
    tmp_path: Path, suffix: str
) -> None:
    photo = tmp_path / f"cover{suffix}"
    photo.write_bytes(b"photo")
    with pytest.raises(ValueError, match="unsupported cover image type"):
        book_metadata._image_content_block(photo)
