from __future__ import annotations

import base64
import json
import mimetypes
import os
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib import request

from .config import RAW_DATA_ROOT


PLACEHOLDER = "[IMAGE_PLACEHOLDER_{index}]"
MANIFEST_SUFFIX = ".images.json"
IMAGE_EXTENSIONS = {
    ".avif",
    ".bmp",
    ".gif",
    ".heic",
    ".heif",
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
MARKDOWN_IMAGE = re.compile(r"!\[[^\]\n]*\]\(([^)\n]+)\)")
PLACEHOLDER_TOKEN = re.compile(r"\[IMAGE_PLACEHOLDER_(\d+)\]")


@dataclass
class ImagePlaceholder:
    index: int
    token: str
    kind: str
    original: str
    image_path: str | None
    candidate_text: str = ""
    candidate_source: str = "pending"
    approved: bool = False
    approved_text: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def processing_root() -> Path:
    return RAW_DATA_ROOT / "processing"


def manifest_path(working_path: Path) -> Path:
    return working_path.with_name(f"{working_path.name}{MANIFEST_SUFFIX}")


def resolve_processing_path(relative_path: str) -> Path:
    root = processing_root().resolve()
    path = (root / relative_path).resolve()
    if path != root and root not in path.parents:
        raise ValueError("processing path escapes Raw Data/processing")
    if not path.is_file():
        raise FileNotFoundError(relative_path)
    return path


def is_manifest(path: Path) -> bool:
    return path.name.endswith(MANIFEST_SUFFIX)


def is_text_document(path: Path) -> bool:
    if path.suffix.lower() not in TEXT_EXTENSIONS:
        return False
    try:
        sample = path.read_bytes()[:4096]
    except OSError:
        return False
    return b"\x00" not in sample


def is_image_file(path: Path) -> bool:
    return path.suffix.lower() in IMAGE_EXTENSIONS


def prepare_document(relative_path: str) -> dict:
    path = resolve_processing_path(relative_path)
    return prepare_document_path(path)


def prepare_document_path(path: Path) -> dict:
    if is_manifest(path):
        return document_state(path, [])

    placeholders = load_manifest(path)
    changed = False

    if is_text_document(path):
        text = path.read_text(encoding="utf-8")
        text, inserted = insert_placeholders(path, text, placeholders)
        if inserted:
            path.write_text(text, encoding="utf-8")
            placeholders.extend(inserted)
            changed = True
        synced = sync_existing_tokens(text, placeholders)
        changed = changed or ([item.to_dict() for item in synced] != [item.to_dict() for item in placeholders])
        placeholders = synced
    elif is_image_file(path):
        if not placeholders:
            placeholders = [
                ImagePlaceholder(
                    index=1,
                    token=PLACEHOLDER.format(index=1),
                    kind="whole_page",
                    original=path.name,
                    image_path=str(path),
                )
            ]
            changed = True

    if changed and placeholders:
        save_manifest(path, placeholders)
    return document_state(path, placeholders)


def document_status_path(path: Path) -> dict:
    state = prepare_document_path(path)
    return {
        "image_count": len(state["placeholders"]),
        "unresolved_image_count": sum(
            1 for item in state["placeholders"] if not item["approved"]
        ),
    }


def read_document_images(relative_path: str) -> dict:
    return prepare_document(relative_path)


def approve_placeholder(relative_path: str, index: int, approved_text: str) -> dict:
    path = resolve_processing_path(relative_path)
    placeholders = load_manifest(path)
    match = next((item for item in placeholders if item.index == index), None)
    if match is None:
        raise ValueError(f"unknown image placeholder: {index}")

    if is_text_document(path):
        text = path.read_text(encoding="utf-8")
        if match.token not in text and not match.approved:
            raise ValueError(f"placeholder token missing from working copy: {match.token}")
        if match.token in text:
            text = text.replace(match.token, approved_text, 1)
            path.write_text(text, encoding="utf-8")

    match.approved = True
    match.approved_text = approved_text
    match.candidate_text = approved_text
    match.candidate_source = "approved"
    save_manifest(path, placeholders)
    return document_state(path, placeholders)


def candidate_for_placeholder(relative_path: str, index: int) -> dict:
    path = resolve_processing_path(relative_path)
    placeholders = load_manifest(path)
    match = next((item for item in placeholders if item.index == index), None)
    if match is None:
        raise ValueError(f"unknown image placeholder: {index}")
    if match.candidate_text:
        return match.to_dict()

    image_path = Path(match.image_path) if match.image_path else None
    if image_path and image_path.exists() and match.kind == "whole_page":
        text = ocr_candidate(image_path)
        source = "ocr"
    elif image_path and image_path.exists():
        text = vision_candidate(image_path)
        source = "vision" if text else "manual"
    else:
        text = ""
        source = "missing"

    match.candidate_text = text
    match.candidate_source = source
    save_manifest(path, placeholders)
    return match.to_dict()


def image_path_for_placeholder(relative_path: str, index: int) -> Path:
    path = resolve_processing_path(relative_path)
    placeholders = load_manifest(path)
    match = next((item for item in placeholders if item.index == index), None)
    if match is None or not match.image_path:
        raise FileNotFoundError(index)
    image_path = Path(match.image_path)
    if not image_path.exists():
        raise FileNotFoundError(str(image_path))
    return image_path


def load_manifest(path: Path) -> list[ImagePlaceholder]:
    sidecar = manifest_path(path)
    if not sidecar.exists():
        return []
    data = json.loads(sidecar.read_text(encoding="utf-8"))
    return [ImagePlaceholder(**item) for item in data.get("placeholders", [])]


def save_manifest(path: Path, placeholders: list[ImagePlaceholder]) -> None:
    sidecar = manifest_path(path)
    payload = {
        "version": 1,
        "working_path": str(path),
        "placeholders": [item.to_dict() for item in sorted(placeholders, key=lambda x: x.index)],
    }
    sidecar.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def document_state(path: Path, placeholders: list[ImagePlaceholder]) -> dict:
    root = processing_root().resolve()
    return {
        "path": path.relative_to(root).as_posix(),
        "placeholders": [item.to_dict() for item in sorted(placeholders, key=lambda x: x.index)],
    }


def insert_placeholders(
    working_path: Path, text: str, existing: list[ImagePlaceholder]
) -> tuple[str, list[ImagePlaceholder]]:
    matches = image_reference_matches(text)
    if not matches:
        return text, []

    next_index = max([item.index for item in existing] + [0]) + 1
    inserted: list[ImagePlaceholder] = []
    chunks = []
    cursor = 0
    for start, end, original, target in matches:
        chunks.append(text[cursor:start])
        token = PLACEHOLDER.format(index=next_index)
        image_path = resolve_embedded_image(working_path, target)
        chunks.append(token)
        inserted.append(
            ImagePlaceholder(
                index=next_index,
                token=token,
                kind="embedded",
                original=original,
                image_path=str(image_path) if image_path else None,
            )
        )
        next_index += 1
        cursor = end
    chunks.append(text[cursor:])
    return "".join(chunks), inserted


def image_reference_matches(text: str) -> list[tuple[int, int, str, str]]:
    matches: list[tuple[int, int, str, str]] = []
    for match in OBSIDIAN_EMBED.finditer(text):
        target = match.group(1).split("|", 1)[0].split("#", 1)[0].strip()
        if Path(target).suffix.lower() in IMAGE_EXTENSIONS:
            matches.append((match.start(), match.end(), match.group(0), target))
    for match in MARKDOWN_IMAGE.finditer(text):
        target = match.group(1).strip().strip("<>")
        if target.lower().startswith(("http://", "https://")):
            continue
        if Path(target).suffix.lower() in IMAGE_EXTENSIONS:
            matches.append((match.start(), match.end(), match.group(0), target))
    return sorted(matches, key=lambda item: item[0])


def sync_existing_tokens(
    text: str, placeholders: list[ImagePlaceholder]
) -> list[ImagePlaceholder]:
    by_index = {item.index: item for item in placeholders}
    for match in PLACEHOLDER_TOKEN.finditer(text):
        index = int(match.group(1))
        if index not in by_index:
            by_index[index] = ImagePlaceholder(
                index=index,
                token=PLACEHOLDER.format(index=index),
                kind="embedded",
                original="",
                image_path=None,
            )
    return sorted(by_index.values(), key=lambda item: item.index)


def resolve_embedded_image(working_path: Path, target: str) -> Path | None:
    candidate = Path(target).expanduser()
    if candidate.is_absolute() and candidate.exists():
        return candidate.resolve()

    local = (working_path.parent / target).resolve()
    if local.exists():
        return local

    inbox = RAW_DATA_ROOT / "inbox"
    if inbox.exists():
        matches = sorted(inbox.rglob(Path(target).name))
        for match in matches:
            if match.is_file():
                return match.resolve()
    return None


def ocr_candidate(image_path: Path) -> str:
    page_scanner_root = RAW_DATA_ROOT.parent.parent / "Automation Personal" / "Page Scanner"
    if str(page_scanner_root) not in sys.path:
        sys.path.insert(0, str(page_scanner_root))
    from core import images as page_images  # noqa: WPS433
    from core import ocr  # noqa: WPS433

    img = page_images.load_image(image_path)
    words = ocr.ocr_page(img)
    return " ".join(word["text"] for word in words).strip()


def vision_candidate(image_path: Path) -> str:
    gateway = os.environ.get("LLM_GATEWAY_V7_URL", "http://localhost:8107").rstrip("/")
    mime_type = mimetypes.guess_type(str(image_path))[0] or "application/octet-stream"
    encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
    data_url = f"data:{mime_type};base64,{encoded}"
    body = {
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "Transcribe the visible content of this image for insertion "
                            "into a markdown note. Return only the transcription."
                        ),
                    },
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }
        ],
        "provider": os.environ.get("LLM_GATEWAY_VISION_PROVIDER"),
        "max_tokens": 1000,
        "temperature": 0,
    }
    body = {key: value for key, value in body.items() if value is not None}
    data = json.dumps(body).encode("utf-8")
    try:
        req = request.Request(
            f"{gateway}/v1/chat",
            data=data,
            headers={"content-type": "application/json"},
            method="POST",
        )
        with request.urlopen(req, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        return ""
    return str(payload.get("text") or "").strip()
