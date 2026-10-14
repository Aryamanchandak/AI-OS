from __future__ import annotations

import difflib
import hashlib
import inspect
import json
import re
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from .config import RAW_DATA_ROOT, SOURCE_REGISTRY
from . import images as image_review


IMAGE_EXTENSIONS = {
    ".avif",
    ".bmp",
    ".gif",
    ".heic",
    ".jpeg",
    ".jpg",
    ".png",
    ".svg",
    ".tif",
    ".tiff",
    ".webp",
}
TEXT_EXTENSIONS = {
    ".adoc",
    ".csv",
    ".json",
    ".jsonl",
    ".log",
    ".md",
    ".rst",
    ".text",
    ".tsv",
    ".txt",
    ".yaml",
    ".yml",
}
OBSIDIAN_EMBED = re.compile(r"!\[\[([^\]\n]+)\]\]")
MARKDOWN_IMAGE = re.compile(r"!\[[^\]\n]*\]\([^)]+\)")
DIAGRAM_HINT = re.compile(
    r"```(?:mermaid|plantuml|graphviz|dot|d2)\b|!\[\[[^\]\n]*\.excalidraw(?:\.md)?\]\]",
    re.IGNORECASE,
)
WORKING_FINGERPRINT = re.compile(r"--([0-9a-f]{16})(?:\.[^.]+)?$")
_DB_PATH = RAW_DATA_ROOT.parent / "sqlite" / "ledger.db"
DEFAULT_OBSIDIAN_CONFIG = (
    Path.home() / "Library" / "Application Support" / "obsidian" / "obsidian.json"
)


@dataclass(frozen=True)
class ReviewItem:
    path: str
    name: str
    size: int
    modified_at: float
    editable: bool
    contains_images: bool
    image_count: int
    unresolved_image_count: int
    edited_obsidian_note: bool
    route_hint: str

    def to_dict(self) -> dict:
        return asdict(self)


def processing_root() -> Path:
    return RAW_DATA_ROOT / "processing"


def init_glossary() -> None:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(_DB_PATH)) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS glossary("
            "shorthand TEXT, expansion TEXT, updated_at TEXT)"
        )


def glossary_entries() -> list[dict]:
    init_glossary()
    with sqlite3.connect(str(_DB_PATH)) as conn:
        rows = conn.execute(
            """SELECT shorthand, expansion, MAX(updated_at) AS updated_at
               FROM glossary
               GROUP BY shorthand, expansion
               ORDER BY lower(shorthand), lower(expansion)"""
        ).fetchall()
    return [
        {"shorthand": row[0], "expansion": row[1], "updated_at": row[2]}
        for row in rows
    ]


def apply_glossary(
    relative_path: str,
    shorthand: str,
    expansion: str,
    confirmed: bool = False,
) -> dict:
    shorthand = shorthand.strip()
    expansion = expansion.strip()
    if not shorthand:
        raise ValueError("shorthand is required")
    if not expansion:
        raise ValueError("expansion is required")

    path = resolve_processing_path(relative_path)
    if not is_editable(path):
        raise ValueError(f"processing item is not editable text: {relative_path}")

    text = path.read_text(encoding="utf-8")
    pattern = re.compile(r"\b" + re.escape(shorthand) + r"\b")
    updated, count = pattern.subn(expansion, text)
    if count:
        path.write_text(updated, encoding="utf-8")

    if confirmed:
        remember_glossary(shorthand, expansion)

    return {
        "item": read_item(relative_path),
        "replacement_count": count,
        "glossary": glossary_entries(),
    }


def remember_glossary(shorthand: str, expansion: str) -> None:
    init_glossary()
    now = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(str(_DB_PATH)) as conn:
        conn.execute(
            "DELETE FROM glossary WHERE shorthand = ? AND expansion = ?",
            (shorthand, expansion),
        )
        conn.execute(
            "INSERT INTO glossary(shorthand, expansion, updated_at) VALUES(?,?,?)",
            (shorthand, expansion, now),
        )


def approve_item(relative_path: str, final_text: str | None = None) -> dict:
    path = resolve_processing_path(relative_path)
    if not is_editable(path):
        raise ValueError(f"processing item is not editable text: {relative_path}")

    image_status = image_review.document_status_path(path)
    if image_status["unresolved_image_count"]:
        raise ValueError("cannot approve item with unresolved image placeholders")

    if final_text is not None and not is_generated_diff_payload(path, final_text):
        path.write_text(final_text, encoding="utf-8")
    body = path.read_text(encoding="utf-8")
    source_path = obsidian_source_path_for_working_file(path)
    capture_source = obsidian_capture_source() if source_path else "highlight"

    result = call_capture(body=body, source=capture_source, authored=True)
    if source_path:
        record_note_lineage(
            source_path=source_path,
            content_hash=result.content_hash,
            captured_at=datetime.now(timezone.utc).isoformat(),
        )

    return {
        "ok": True,
        "source": capture_source,
        "source_path": source_path,
        "duplicate": result.duplicate,
        "content_hash": result.content_hash,
        "item_id": result.item_id,
        "path": result.path,
    }


def call_capture(body: str, source: str, authored: bool):
    from .capture import capture
    from .ledger import init_ledger

    init_ledger()
    parameters = inspect.signature(capture).parameters
    if "body" in parameters:
        return capture(body=body, source=source, authored=authored)
    return capture(source=source, content=body, authored=authored)


def record_note_lineage(source_path: str, content_hash: str, captured_at: str) -> None:
    with sqlite3.connect(str(_DB_PATH)) as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS note_lineage(
                   source_path TEXT, content_hash TEXT, captured_at TEXT
               )"""
        )
        conn.execute(
            "INSERT INTO note_lineage(source_path, content_hash, captured_at) VALUES(?,?,?)",
            (source_path, content_hash, captured_at),
        )


def list_items() -> list[dict]:
    root = processing_root()
    if not root.exists():
        return []

    items = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if image_review.is_manifest(path):
            continue
        item = classify_item(path, root)
        items.append(item.to_dict())
    return items


def read_item(relative_path: str) -> dict:
    path = resolve_processing_path(relative_path)
    item = classify_item(path, processing_root())
    if not item.editable:
        return {**item.to_dict(), "content": "", "encoding": "binary"}
    working_content = path.read_text(encoding="utf-8")
    diff_review = diff_review_for_path(path, working_content)
    if diff_review:
        return {
            **item.to_dict(),
            "content": diff_review["diff"],
            "working_content": working_content,
            "review_mode": "diff",
            "diff_review": diff_review,
            "encoding": "utf-8",
        }
    return {
        **item.to_dict(),
        "content": working_content,
        "working_content": working_content,
        "review_mode": "full",
        "diff_review": None,
        "encoding": "utf-8",
    }


def save_item(relative_path: str, content: str) -> dict:
    path = resolve_processing_path(relative_path)
    if not is_editable(path):
        raise ValueError(f"processing item is not editable text: {relative_path}")
    if is_generated_diff_payload(path, content):
        return read_item(relative_path)
    path.write_text(content, encoding="utf-8")
    return read_item(relative_path)


def is_generated_diff_payload(path: Path, content: str) -> bool:
    if not is_editable(path):
        return False
    try:
        working_content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return False
    diff_review = diff_review_for_path(path, working_content)
    return bool(diff_review and content == diff_review["diff"])


def diff_review_for_path(path: Path, current_text: str | None = None) -> dict | None:
    source_path = obsidian_source_path_for_working_file(path)
    if not source_path:
        return None

    lineage = latest_note_lineage(source_path)
    if not lineage:
        return None

    prior_text = prior_text_for_content_hash(lineage["content_hash"])
    if prior_text is None:
        return None

    if current_text is None:
        if not is_editable(path):
            return None
        try:
            current_text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return None

    if current_text == prior_text:
        return None

    diff_text = line_diff(prior_text, current_text)
    return {
        "source_path": source_path,
        "prior_content_hash": lineage["content_hash"],
        "prior_captured_at": lineage["captured_at"],
        "diff": diff_text,
    }


def latest_note_lineage(source_path: str) -> dict | None:
    if not _DB_PATH.exists():
        return None
    try:
        with sqlite3.connect(str(_DB_PATH)) as conn:
            row = conn.execute(
                """SELECT content_hash, captured_at
                   FROM note_lineage
                   WHERE source_path = ?
                   ORDER BY captured_at DESC, rowid DESC
                   LIMIT 1""",
                (source_path,),
            ).fetchone()
    except sqlite3.OperationalError:
        return None
    if not row:
        return None
    return {"content_hash": row[0], "captured_at": row[1]}


def prior_text_for_content_hash(content_hash: str) -> str | None:
    if not _DB_PATH.exists():
        return None
    try:
        with sqlite3.connect(str(_DB_PATH)) as conn:
            row = conn.execute(
                "SELECT bronze_path FROM items WHERE content_hash = ?",
                (content_hash,),
            ).fetchone()
    except sqlite3.OperationalError:
        return None
    if not row:
        return None

    bronze_path = RAW_DATA_ROOT / row[0]
    try:
        bronze_text = bronze_path.read_text(encoding="utf-8")
    except OSError:
        return None
    return strip_frontmatter(bronze_text)


def strip_frontmatter(text: str) -> str:
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return text
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return "".join(lines[index + 1 :])
    return text


def line_diff(prior_text: str, current_text: str) -> str:
    diff_lines = difflib.unified_diff(
        prior_text.splitlines(),
        current_text.splitlines(),
        fromfile="previous",
        tofile="current",
        lineterm="",
        n=0,
    )
    return "\n".join(diff_lines) + "\n"


def resolve_processing_path(relative_path: str) -> Path:
    root = processing_root().resolve()
    path = (root / relative_path).resolve()
    if path != root and root not in path.parents:
        raise ValueError("processing path escapes Raw Data/processing")
    if not path.is_file():
        raise FileNotFoundError(relative_path)
    return path


def classify_item(path: Path, root: Path) -> ReviewItem:
    stat = path.stat()
    relative = path.resolve().relative_to(root.resolve())
    image_status = image_review.document_status_path(path)
    contains_images = image_status["image_count"] > 0 or item_contains_images(path)
    source_path = obsidian_source_path_for_working_file(path)
    prior = latest_note_lineage(source_path) if source_path else None
    edited_note = prior is not None
    unresolved = image_status["unresolved_image_count"]
    route_hint = "image_review" if unresolved else "text_review"
    if not unresolved and is_editable(path) and diff_review_for_path(path):
        route_hint = "diff_review"
    return ReviewItem(
        path=relative.as_posix(),
        name=path.name,
        size=stat.st_size,
        modified_at=stat.st_mtime,
        editable=is_editable(path),
        contains_images=contains_images,
        image_count=image_status["image_count"],
        unresolved_image_count=unresolved,
        edited_obsidian_note=edited_note,
        route_hint=route_hint,
    )


def item_contains_images(path: Path) -> bool:
    if path.suffix.lower() in IMAGE_EXTENSIONS:
        return True
    if not is_editable(path):
        return False

    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return False

    return bool(
        obsidian_embed_has_image(text)
        or MARKDOWN_IMAGE.search(text)
        or DIAGRAM_HINT.search(text)
    )


def obsidian_embed_has_image(text: str) -> bool:
    for match in OBSIDIAN_EMBED.finditer(text):
        target = match.group(1).split("|", 1)[0].split("#", 1)[0].strip()
        suffix = Path(target).suffix.lower()
        if suffix in IMAGE_EXTENSIONS or suffix in {".excalidraw", ".svg"}:
            return True
    return False


def is_editable(path: Path) -> bool:
    if path.suffix.lower() not in TEXT_EXTENSIONS:
        return False
    try:
        with path.open("rb") as file:
            sample = file.read(4096)
    except OSError:
        return False
    return b"\x00" not in sample


def source_path_fingerprints() -> set[str]:
    if not _DB_PATH.exists():
        return set()
    try:
        with sqlite3.connect(str(_DB_PATH)) as conn:
            rows = conn.execute(
                "SELECT source_path FROM note_lineage WHERE source_path IS NOT NULL"
            ).fetchall()
    except sqlite3.OperationalError:
        return set()
    return {fingerprint_source_path(row[0]) for row in rows if row[0]}


def source_path_fingerprint(path: Path) -> str | None:
    match = WORKING_FINGERPRINT.search(path.stem)
    return match.group(1) if match else None


def fingerprint_source_path(source_path: str) -> str:
    normalized = str(Path(source_path).expanduser().resolve())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def obsidian_capture_source() -> str:
    if "obsidian" in SOURCE_REGISTRY.values():
        return "obsidian"
    return "note"


def obsidian_source_path_for_working_file(path: Path) -> str | None:
    fingerprint = source_path_fingerprint(path)
    if not fingerprint:
        return None

    inbox_root = RAW_DATA_ROOT / "inbox"
    if not inbox_root.exists():
        return None

    for mirrored in sorted(inbox_root.rglob("*")):
        if not mirrored.is_file():
            continue
        if fingerprint_source_path(str(mirrored)) != fingerprint:
            continue
        return vault_path_for_mirrored_file(mirrored)
    return None


def vault_path_for_mirrored_file(mirrored: Path) -> str:
    try:
        relative = mirrored.resolve().relative_to((RAW_DATA_ROOT / "inbox").resolve())
    except ValueError:
        return str(mirrored.resolve())

    vault = discover_vault_path()
    if vault:
        return str((vault / relative).resolve())
    return str(mirrored.resolve())


def discover_vault_path(obsidian_config: Path = DEFAULT_OBSIDIAN_CONFIG) -> Path | None:
    try:
        data = json.loads(obsidian_config.expanduser().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    vaults = data.get("vaults", {})
    if not isinstance(vaults, dict):
        return None

    paths: list[Path] = []
    for vault in vaults.values():
        if isinstance(vault, dict) and isinstance(vault.get("path"), str):
            paths.append(Path(vault["path"]).expanduser())

    for candidate in paths:
        if candidate.exists():
            return candidate.resolve()
    return paths[0].resolve() if paths else None
