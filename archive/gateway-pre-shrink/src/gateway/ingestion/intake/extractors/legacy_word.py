from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
import subprocess
import tempfile

from docx import Document

from gateway.ingestion.intake.base import IntakeResult
from gateway.ingestion.intake.extractors.word import extract_docx_document

ConvertToDocx = Callable[[Path, Path], None]
DetectTables = Callable[[Path], bool | None]


class DocConversionError(RuntimeError):
    """A legacy .doc file could not be converted to .docx for parsing."""


def _textutil_convert(source: Path, destination: Path) -> None:
    try:
        completed = subprocess.run(
            ["textutil", "-convert", "docx", "-output", str(destination), str(source)],
            capture_output=True,
            check=False,
        )
    except FileNotFoundError as exc:
        raise DocConversionError(
            "legacy .doc extraction requires macOS's textutil, which was not "
            "found on PATH"
        ) from exc

    if completed.returncode != 0 or not destination.exists():
        stderr = completed.stderr.decode("utf-8", errors="replace").strip()
        raise DocConversionError(
            f"textutil failed to convert {source.name!r} to .docx"
            + (f": {stderr}" if stderr else "")
        )


def _textutil_has_table(source: Path) -> bool | None:
    """Best-effort check for tables textutil's .docx export would flatten.

    ``textutil -convert docx`` silently drops table structure (rows/cells
    collapse into a flat run of paragraphs) even though the same source
    file's HTML export keeps a real ``<table>`` -- confirmed by round-trip
    testing, not assumed. This runs that HTML export separately, purely to
    detect the loss, and returns None if detection itself is inconclusive
    (never raises: the primary conversion already succeeded by the time
    this runs, and a failed check should not fail the whole extraction).
    """

    try:
        completed = subprocess.run(
            ["textutil", "-convert", "html", "-stdout", str(source)],
            capture_output=True,
            check=False,
        )
    except OSError:
        return None
    if completed.returncode != 0:
        return None
    return b"<table" in completed.stdout.lower()


class LegacyWordExtractor:
    """Extract .doc (Word 97-2003 binary/OLE format) via textutil -> WordExtractor.

    python-docx only reads the OOXML format (.docx) -- it cannot open the
    legacy binary format at all. macOS ships ``textutil``, which converts
    .doc to real .docx with no extra runtime dependency; the result is then
    parsed with the same paragraph/heading logic used for native .docx
    files.

    This is NOT lossless parity with native .docx, and callers should not
    assume it is: textutil's .doc -> .docx conversion flattens tables into
    plain paragraphs and does not preserve Word heading styles, even though
    no text is dropped (every cell's text still comes through, just without
    row/column structure). When a source .doc appears to contain a table,
    this is surfaced via ``needs_approval`` rather than silently returned as
    if it were structurally intact.
    """

    def __init__(
        self,
        convert_to_docx: ConvertToDocx | None = None,
        detect_tables: DetectTables | None = None,
    ) -> None:
        self._convert = convert_to_docx or _textutil_convert
        self._detect_tables = detect_tables or _textutil_has_table

    def handles(self, path: Path) -> bool:
        return path.is_file() and path.suffix.lower() == ".doc"

    def extract(self, path: Path) -> IntakeResult:
        has_table = self._detect_tables(path)
        extra_reasons: list[str] = []
        if has_table:
            extra_reasons.append(
                "legacy .doc appears to contain a table; textutil's .docx "
                "conversion flattens tables into plain paragraphs, so "
                "row/column structure may be lost"
            )
        elif has_table is None:
            extra_reasons.append(
                "could not verify whether this .doc contained a table that "
                "textutil's .docx conversion would flatten"
            )

        with tempfile.TemporaryDirectory() as tmp_dir:
            converted = Path(tmp_dir) / f"{path.stem}.docx"
            self._convert(path, converted)
            document = Document(str(converted))
            return extract_docx_document(
                document,
                source_path=path,
                extraction_method="doc_textutil_conversion",
                extra_reasons=extra_reasons,
            )


def extract_legacy_word(
    path: Path,
    *,
    convert_to_docx: ConvertToDocx | None = None,
    detect_tables: DetectTables | None = None,
) -> IntakeResult:
    return LegacyWordExtractor(
        convert_to_docx=convert_to_docx, detect_tables=detect_tables
    ).extract(path)
