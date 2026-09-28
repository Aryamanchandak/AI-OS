"""Image extractor backed by the Page Scanner photo pipeline."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from gateway.ingestion.intake.base import IntakeResult
from gateway.ingestion.sources import book_metadata
from gateway.ingestion.sources.page_scanner import cleanup
from gateway.ingestion.sources.page_scanner.detect import HsvFloor
from gateway.ingestion.sources.page_scanner.photo_pipeline import PhotoResult, process_photo


IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".heic",
    ".heif",
    ".tiff",
    ".tif",
    ".bmp",
}

PhotoProcessor = Callable[..., PhotoResult]
PassageCleaner = Callable[[list[str]], list[str]]


class ImageExtractor:
    """Extract highlighted passages; every OCR result requires approval."""

    def __init__(
        self,
        *,
        hsv_params: HsvFloor | None = None,
        clean: bool = False,
        processor: PhotoProcessor = process_photo,
        cleaner: PassageCleaner | None = None,
        cleanup_client: cleanup.ChatClient | None = None,
        cleanup_profile: str = cleanup.DEFAULT_CLEANUP_PROFILE,
        metadata_client: book_metadata.ChatClient | None = None,
    ) -> None:
        self.hsv_params = hsv_params
        self.clean = clean
        self._processor = processor
        self._cleaner = cleaner
        self._cleanup_client = cleanup_client
        self._cleanup_profile = cleanup_profile
        self._metadata_client = metadata_client

    def handles(self, path: Path) -> bool:
        return path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS

    def extract(self, path: Path) -> IntakeResult:
        photo = self._processor(path, hsv_params=self.hsv_params)
        raw_texts = [passage.text for passage in photo.passages]
        if not self.clean:
            edited_texts = raw_texts
        elif self._cleaner is not None:
            edited_texts = self._cleaner(raw_texts)
        else:
            edited_texts = cleanup.clean_passages(
                raw_texts,
                chat_client=self._cleanup_client,
                profile=self._cleanup_profile,
            )
        if len(edited_texts) != len(raw_texts):
            raise RuntimeError("photo cleanup changed the number of passages")

        no_passages = not raw_texts
        reason = "photo OCR requires approval"
        if no_passages:
            reason = "no highlighted passages were detected; RETAKE review required"
        elif photo.flagged_retake:
            reason = "photo failed the quality gate and requires RETAKE review"
        metadata = book_metadata.load_or_resolve(
            path.parent, chat_client=self._metadata_client
        )
        return IntakeResult(
            markdown_text="\n\n".join(edited_texts),
            title=path.stem,
            needs_approval=True,
            approval_reason=reason,
            frontmatter={
                "source_filename": path.name,
                "extraction_method": "photo_ocr",
                "book_meta": metadata,
                "page_scanner": {
                    "file_hash": photo.file_hash,
                    "blur_score": photo.blur_score,
                    "glare_score": photo.glare_score,
                    "conf_ratio": photo.conf_ratio,
                    # A zero-result detector is never a successful scan.  It
                    # must not travel through approval and archive the only
                    # photo while producing no highlight.
                    "flagged_retake": photo.flagged_retake or no_passages,
                    "passages": [
                        {
                            "text": passage.text,
                            "edited_text": edited,
                            "bbox": passage.bbox,
                            "min_conf": passage.min_conf,
                        }
                        for passage, edited in zip(photo.passages, edited_texts)
                    ],
                },
            },
        )


def extract_image(path: Path) -> IntakeResult:
    return ImageExtractor().extract(path)
