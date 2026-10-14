from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, cast

import pymupdf

from ingestion.intake.base import IntakeResult, text_sanity_issue


OcrPage = Callable[[pymupdf.Pixmap], Sequence[dict[str, Any]]]
MIN_TEXT_LAYER_CHARACTERS = 3


class OcrUnavailableError(RuntimeError):
    """A PDF needs OCR but Component 2's OCR adapter is not available."""


def _default_ocr_page(pixmap: pymupdf.Pixmap) -> Sequence[dict[str, Any]]:
    try:
        from ingestion.sources.page_scanner.ocr import ocr_lines
    except (ImportError, ModuleNotFoundError) as exc:
        raise OcrUnavailableError(
            "scanned PDF requires ingestion.sources.page_scanner.ocr.ocr_lines; "
            "install Component 2 or inject ocr_lines into PdfExtractor"
        ) from exc
    image = pixmap.pil_image()  # type: ignore[no-untyped-call]
    try:
        return cast(Sequence[dict[str, Any]], ocr_lines(image))
    finally:
        image.close()


def _has_usable_text_layer(text: str) -> bool:
    return len("".join(text.split())) >= MIN_TEXT_LAYER_CHARACTERS


class PdfExtractor:
    """Use embedded PDF text when present and OCR only image-only pages."""

    def __init__(self, ocr_lines: OcrPage | None = None) -> None:
        self._ocr_page = ocr_lines or _default_ocr_page

    def handles(self, path: Path) -> bool:
        return path.is_file() and path.suffix.lower() == ".pdf"

    def extract(self, path: Path) -> IntakeResult:
        page_text: list[str] = []
        ocr_page_numbers: list[int] = []

        with pymupdf.open(path) as document:  # type: ignore[no-untyped-call]
            native_page_text = [page.get_text() for page in document]
            document_has_native_text = any(
                _has_usable_text_layer(text) for text in native_page_text
            )
            for page_number, page in enumerate(document, start=1):
                native_text = native_page_text[page_number - 1]
                if _has_usable_text_layer(native_text):
                    page_text.append(native_text.strip())
                    continue

                has_visual_content = bool(
                    page.get_images(full=True) or page.get_drawings()
                )
                if document_has_native_text and not has_visual_content:
                    # Do not turn an intentionally blank page in an otherwise
                    # native PDF into a false OCR/approval event.
                    continue

                pixmap = page.get_pixmap(alpha=False)
                lines = self._ocr_page(pixmap)
                page_text.append(
                    "\n".join(
                        str(line.get("text", "")).strip()
                        for line in lines
                        if str(line.get("text", "")).strip()
                    )
                )
                ocr_page_numbers.append(page_number)

        markdown_text = "\n\n".join(text for text in page_text if text)
        sanity_issue = text_sanity_issue(markdown_text)
        reasons: list[str] = []
        if ocr_page_numbers:
            pages = ", ".join(str(number) for number in ocr_page_numbers)
            reasons.append(f"scanned PDF page(s) required OCR: {pages}")
        if sanity_issue:
            reasons.append(sanity_issue)

        return IntakeResult(
            markdown_text=markdown_text,
            title=path.stem,
            needs_approval=bool(reasons),
            approval_reason="; ".join(reasons) or None,
            frontmatter={
                "source_filename": path.name,
                "extraction_method": (
                    "pdf_ocr" if ocr_page_numbers else "pdf_text_layer"
                ),
                "ocr_pages": ocr_page_numbers,
            },
        )


def extract_pdf(path: Path, *, ocr_lines: OcrPage | None = None) -> IntakeResult:
    return PdfExtractor(ocr_lines=ocr_lines).extract(path)
