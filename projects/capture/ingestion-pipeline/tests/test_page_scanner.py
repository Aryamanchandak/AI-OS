from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image
import pytest

from ingestion.intake.extractors.image import ImageExtractor
from ingestion.intake.funnel import default_extractors, route_file, run_funnel
from ingestion.sources import book_metadata
from ingestion.sources.page_scanner import cleanup, images, quality, store
from ingestion.sources.page_scanner.photo_pipeline import (
    BELOW_REACH_FRAC,
    BODY_FAINT_FRAC,
    BODY_SOLID_FRAC,
    EDGE_MARGIN_FRAC,
    KEEP_OVERLAP_FRAC,
    LOW_CONF,
    MIN_PASSAGE_WORDS,
    PASSAGE_GAP_LINEHEIGHTS,
    WORD_PAD_DOWN_FRAC,
    WORD_PAD_UP_FRAC,
    Passage,
    PhotoResult,
    _build_passages,
    _keep_words,
    process_photo,
)


def _word(
    text: str,
    bbox: list[int],
    *,
    confidence: float = 1.0,
) -> dict[str, Any]:
    return {"text": text, "bbox": bbox, "confidence": confidence}


def _working_word(
    text: str,
    bbox: list[int],
    *,
    center_y: float,
    padded_height: float = 14.0,
    confidence: float = 1.0,
) -> dict[str, Any]:
    return {
        "text": text,
        "bbox": bbox,
        "confidence": confidence,
        "_body": 1.0,
        "_cy": center_y,
        "_ph": padded_height,
    }


def test_tuning_constants_are_ported_without_retuning() -> None:
    assert WORD_PAD_DOWN_FRAC == 0.35
    assert WORD_PAD_UP_FRAC == 0.10
    assert KEEP_OVERLAP_FRAC == 0.10
    assert PASSAGE_GAP_LINEHEIGHTS == 1.5
    assert BODY_SOLID_FRAC == 0.30
    assert BODY_FAINT_FRAC == 0.08
    assert BELOW_REACH_FRAC == 1.3
    assert EDGE_MARGIN_FRAC == 0.06
    assert MIN_PASSAGE_WORDS == 2
    assert LOW_CONF == 0.5
    assert quality.BLUR_MIN == 80.0
    assert quality.GLARE_MAX == 0.04
    assert quality.CONF_RATIO_MAX == 0.3


def test_default_funnel_routes_supported_image_extensions(tmp_path: Path) -> None:
    extensions = (
        ".jpg",
        ".jpeg",
        ".png",
        ".heic",
        ".heif",
        ".tiff",
        ".tif",
        ".bmp",
    )
    for extension in extensions:
        path = tmp_path / f"page{extension}"
        path.touch()
        assert isinstance(route_file(path, default_extractors()), ImageExtractor)


def test_image_loading_applies_exif_orientation_and_rgb_conversion(
    tmp_path: Path,
) -> None:
    path = tmp_path / "sideways.jpg"
    source = Image.new("L", (40, 20), 128)
    exif = Image.Exif()
    exif[274] = 6
    source.save(path, exif=exif)

    loaded = images.load_image(path)
    try:
        assert loaded.size == (20, 40)
        assert loaded.mode == "RGB"
    finally:
        loaded.close()


def test_image_loading_caps_the_long_edge(tmp_path: Path) -> None:
    path = tmp_path / "large.png"
    Image.new("RGB", (4000, 100), "white").save(path)

    loaded = images.load_image(path)
    try:
        assert loaded.size == (images.MAX_LONG_EDGE, 90)
    finally:
        loaded.close()


def test_keep_words_drops_facing_page_edge_bleed() -> None:
    mask = np.full((100, 100), 255, dtype=np.uint8)
    words = [
        _word("edge", [0, 20, 6, 10]),
        _word("body", [20, 20, 20, 10]),
    ]

    kept = _keep_words(words, mask, image_width=100)

    assert [word["text"] for word in kept] == ["body"]


def test_keep_words_drops_poke_up_leak_from_highlight_below() -> None:
    mask = np.zeros((100, 100), dtype=np.uint8)
    mask[22:32, 20:40] = 255
    words = [
        _word("leak", [20, 10, 20, 10]),
        _word("highlighted", [20, 22, 20, 10]),
    ]

    kept = _keep_words(words, mask, image_width=100)

    assert [word["text"] for word in kept] == ["highlighted"]


def test_passage_grouping_dehyphenates_and_drops_single_word_group() -> None:
    kept = [
        _working_word("under-", [10, 10, 20, 10], center_y=10),
        _working_word("stand", [32, 10, 20, 10], center_y=10),
        _working_word("orphan", [10, 80, 20, 10], center_y=80),
    ]
    lines = [
        {"text": "understand", "bbox": [10, 10, 42, 10], "confidence": 0.45}
    ]

    passages = _build_passages(kept, lines)

    assert passages == [
        Passage(text="understand", bbox=[10, 10, 42, 10], min_conf=0.45)
    ]


@pytest.mark.parametrize(
    ("blur", "glare", "confidence_ratio"),
    [
        (quality.BLUR_MIN - 0.01, 0.0, 0.0),
        (quality.BLUR_MIN, quality.GLARE_MAX + 0.01, 0.0),
        (quality.BLUR_MIN, 0.0, quality.CONF_RATIO_MAX + 0.01),
    ],
)
def test_quality_gate_flags_each_failure_independently(
    blur: float, glare: float, confidence_ratio: float
) -> None:
    assert quality.quality_gate(blur, glare, confidence_ratio) is True
    assert quality.quality_gate(
        quality.BLUR_MIN, quality.GLARE_MAX, quality.CONF_RATIO_MAX
    ) is False


def test_process_photo_returns_data_without_persistence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "photo.jpg"
    path.write_bytes(b"photo bytes")
    image = Image.new("RGB", (100, 100), "white")
    mask = np.full((100, 100), 255, dtype=np.uint8)
    words = [
        _word("hello", [20, 20, 20, 10]),
        _word("world", [42, 20, 20, 10]),
    ]
    lines = [
        {"text": "hello world", "bbox": [20, 20, 42, 10], "confidence": 0.5}
    ]

    from ingestion.sources.page_scanner import photo_pipeline

    monkeypatch.setattr(photo_pipeline.images, "file_hash", lambda _path: "digest")
    monkeypatch.setattr(photo_pipeline.images, "load_image", lambda _path: image)
    monkeypatch.setattr(photo_pipeline.quality, "blur_score", lambda _rgb: 100.0)
    monkeypatch.setattr(photo_pipeline.quality, "glare_score", lambda _rgb: 0.0)
    monkeypatch.setattr(photo_pipeline.ocr, "ocr_lines", lambda _image: lines)
    monkeypatch.setattr(photo_pipeline.ocr, "ocr_page", lambda _image: words)
    monkeypatch.setattr(photo_pipeline.detect, "yellow_mask", lambda _rgb, _hsv: mask)

    result = process_photo(path)

    assert result == PhotoResult(
        passages=[Passage("hello world", [20, 20, 42, 10], 0.5)],
        blur_score=100.0,
        glare_score=0.0,
        conf_ratio=1.0,
        flagged_retake=True,
        file_hash="digest",
    )
    assert not list(tmp_path.glob("*.db"))


def test_process_photo_falls_back_to_vision_lines_when_livetext_is_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "photo.jpg"
    path.write_bytes(b"photo bytes")
    image = Image.new("RGB", (100, 100), "white")
    mask = np.zeros((100, 100), dtype=np.uint8)
    mask[20:30, 10:90] = 255
    lines = [
        {
            "text": "highlighted passage",
            "bbox": [10, 20, 80, 10],
            "confidence": 0.9,
        }
    ]

    from ingestion.sources.page_scanner import photo_pipeline

    monkeypatch.setattr(photo_pipeline.images, "file_hash", lambda _path: "digest")
    monkeypatch.setattr(photo_pipeline.images, "load_image", lambda _path: image)
    monkeypatch.setattr(photo_pipeline.quality, "blur_score", lambda _rgb: 100.0)
    monkeypatch.setattr(photo_pipeline.quality, "glare_score", lambda _rgb: 0.0)
    monkeypatch.setattr(photo_pipeline.ocr, "ocr_lines", lambda _image: lines)
    monkeypatch.setattr(photo_pipeline.ocr, "ocr_page", lambda _image: [])
    monkeypatch.setattr(photo_pipeline.detect, "yellow_mask", lambda _rgb, _hsv: mask)

    result = process_photo(path)

    assert [passage.text for passage in result.passages] == [
        "highlighted passage"
    ]


def test_cleanup_uses_shared_client_with_zero_temperature() -> None:
    calls: list[dict[str, Any]] = []

    class FakeClient:
        def chat(self, prompt: str, **kwargs: Any) -> dict[str, str]:
            calls.append({"prompt": prompt, **kwargs})
            return {"text": "The system was broken"}

    raw = "The systern was broken"

    assert cleanup.clean_passages([raw], chat_client=FakeClient()) == [
        "The system was broken"
    ]
    assert calls[0]["prompt"] == raw
    assert calls[0]["system"] == cleanup.SYSTEM_PROMPT
    assert calls[0]["temperature"] == 0
    assert calls[0]["max_tokens"] == cleanup.CLEANUP_MAX_TOKENS
    assert "messages" not in calls[0]


def test_cleanup_sends_each_passage_in_a_fresh_call() -> None:
    prompts: list[str] = []

    class EchoClient:
        def chat(self, prompt: str, **_kwargs: Any) -> dict[str, str]:
            prompts.append(prompt)
            return {"text": prompt}

    passages = ["first independent passage", "second independent passage"]
    assert cleanup.clean_passages(passages, chat_client=EchoClient()) == passages
    assert prompts == passages


def test_cleanup_diff_guard_keeps_raw_and_gateway_failure_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw = "Habits are the compound interest of self-improvement."
    rewrite = "Small routines create major long-term personal growth over time."
    monkeypatch.setattr(
        cleanup, "_call_gateway", lambda _passage, **_kwargs: rewrite
    )
    assert cleanup.clean_passages([raw]) == [raw]

    def fail(_passage: str, **_kwargs: object) -> str:
        raise RuntimeError("gateway down")

    monkeypatch.setattr(cleanup, "_call_gateway", fail)
    with pytest.raises(RuntimeError, match="gateway down"):
        cleanup.clean_passages([raw, "", "  "])


def test_cleanup_gateway_error_is_not_silently_downgraded() -> None:
    class FailedClient:
        def chat(self, *args: object, **kwargs: object) -> dict[str, Any]:
            del args, kwargs
            raise ConnectionError("local model unavailable")

    with pytest.raises(RuntimeError, match="local model unavailable"):
        cleanup.clean_passages(["OCR passage"], chat_client=FailedClient())


def test_image_funnel_parks_passages_and_moves_retake_photo(tmp_path: Path) -> None:
    drop = tmp_path / "drop"
    vault = tmp_path / "vault"
    database = tmp_path / "processed.db"
    drop.mkdir()
    vault.mkdir()
    source = drop / "page.jpg"
    source.write_bytes(b"source photo")

    def fake_processor(_path: Path, *, hsv_params: object) -> PhotoResult:
        assert hsv_params is None
        return PhotoResult(
            passages=[Passage("Highlighted passage", [1, 2, 3, 4], 0.75)],
            blur_score=70.0,
            glare_score=0.01,
            conf_ratio=0.0,
            flagged_retake=True,
            file_hash="photo-hash",
        )

    report = run_funnel(
        drop,
        vault,
        extractors=[ImageExtractor(processor=fake_processor)],
        park_for_review=store.PendingReviewStore(database, batch="Book"),
    )

    assert report.awaiting_approval_count == 1
    retake = drop / "_retake" / "page.jpg"
    assert not source.exists()
    assert retake.exists()
    assert not (drop / "processed").exists()
    pages = store.get_pages(database)
    assert pages[0]["status"] == "retake"
    assert pages[0]["image_path"] == str(retake)
    assert json.loads(pages[0]["book_meta"])["meta_source"] == "none"
    assert store.get_passages(database, pages[0]["id"])[0] == {
        "id": 1,
        "page_id": pages[0]["id"],
        "bbox": [1, 2, 3, 4],
        "color_tag": "yellow",
        "ocr_text": "Highlighted passage",
        "edited_text": "Highlighted passage",
        "min_conf": 0.75,
        "accepted": 0,
    }

    second = run_funnel(
        drop,
        vault,
        extractors=[ImageExtractor(processor=fake_processor)],
        park_for_review=store.PendingReviewStore(database, batch="Book"),
    )
    assert second.awaiting_approval_count == 0
    assert len(store.get_pages(database)) == 1


def test_image_extractor_populates_book_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "page.jpg"
    source.touch()
    expected: dict[str, object] = {
        "title": "Atomic Habits",
        "confidence": "exact",
    }
    calls: list[Path] = []

    def resolve(folder: Path, *, chat_client: object) -> dict[str, object]:
        calls.append(folder)
        assert chat_client is None
        return expected

    def fake_processor(_path: Path, *, hsv_params: object) -> PhotoResult:
        assert hsv_params is None
        return PhotoResult(
            passages=[Passage("Highlighted passage", [1, 2, 3, 4], 0.75)],
            blur_score=100.0,
            glare_score=0.0,
            conf_ratio=0.0,
            flagged_retake=False,
            file_hash="photo-hash",
        )

    monkeypatch.setattr(book_metadata, "load_or_resolve", resolve)
    result = ImageExtractor(processor=fake_processor).extract(source)

    assert calls == [tmp_path]
    assert result.frontmatter["book_meta"] == expected
