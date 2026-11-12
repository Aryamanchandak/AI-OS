from __future__ import annotations

import hashlib
import json
import os
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


class MalformedSourceError(ValueError):
    pass


@dataclass(frozen=True)
class NormalizedSource:
    raw_bytes: bytes
    decoded_content: str
    normalized_content: str
    raw_hash: str
    normalized_hash: str
    normalized_origin: str
    extracted_metadata: dict[str, Any]


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def normalize_origin(origin: str) -> str:
    value = origin.strip()
    try:
        parsed = urlsplit(value)
        parsed_port = parsed.port
    except ValueError as exc:
        raise MalformedSourceError(f"Malformed origin: {exc}") from exc
    if parsed.scheme.lower() in {"http", "https"} and parsed.netloc:
        scheme = parsed.scheme.lower()
        hostname = (parsed.hostname or "").lower()
        port = parsed_port
        netloc = hostname
        if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
            netloc = f"{hostname}:{port}"
        path = parsed.path or "/"
        while "//" in path:
            path = path.replace("//", "/")
        query = urlencode(sorted(parse_qsl(parsed.query, keep_blank_values=True)))
        return urlunsplit((scheme, netloc, path, query, ""))
    expanded = os.path.expanduser(value)
    if value.startswith(("/", "~", ".")) or "/" in value or "\\" in value:
        return str(Path(os.path.normpath(expanded)).resolve(strict=False))
    return value


def _parse_scalar(raw: str) -> Any:
    value = raw.strip()
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    if value.lower() in {"null", "none", "~"}:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value.strip("\"'")


def extract_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    if not content.startswith("---\n"):
        return {}, content
    # Search from 3 -- the newline that closes the opening marker -- so an
    # empty block ("---\n---\n") finds its own closing marker instead of
    # being reported as unterminated.
    end = content.find("\n---\n", 3)
    if end >= 0:
        body = content[end + 5 :]
    elif content.endswith("\n---"):
        # A file may end on its closing marker with no trailing newline.
        end, body = len(content) - 4, ""
    else:
        raise MalformedSourceError("Opening frontmatter marker has no closing marker")
    metadata: dict[str, Any] = {}
    for line_number, line in enumerate(content[4:end].splitlines(), start=2):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            raise MalformedSourceError(f"Malformed frontmatter line {line_number}: missing ':'")
        key, raw_value = line.split(":", 1)
        key = key.strip()
        if not key or any(character.isspace() for character in key):
            raise MalformedSourceError(f"Malformed frontmatter key on line {line_number}")
        metadata[key] = _parse_scalar(raw_value)
    return metadata, body


def normalize_content(content: str) -> str:
    normalized = unicodedata.normalize("NFC", content.replace("\r\n", "\n").replace("\r", "\n"))
    normalized = re.sub(r"[ \t]+$", "", normalized, flags=re.MULTILINE)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    normalized = re.sub(r"^(\s*)[*+](\s+)", r"\1-\2", normalized, flags=re.MULTILINE)
    lines = [line.rstrip() for line in normalized.split("\n")]
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines) + ("\n" if lines else "")


def normalize_source(content: str | bytes, origin: str) -> NormalizedSource:
    if isinstance(content, bytes):
        raw_bytes = content
        try:
            decoded = content.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise MalformedSourceError(f"Source is not valid UTF-8: {exc}") from exc
    else:
        decoded = content
        raw_bytes = content.encode("utf-8", errors="strict")
    decoded = decoded.removeprefix("\ufeff")
    if "\x00" in decoded:
        raise MalformedSourceError("Source contains a NUL byte")
    line_normalized = decoded.replace("\r\n", "\n").replace("\r", "\n")
    metadata, body = extract_frontmatter(line_normalized)
    normalized = normalize_content(body)
    return NormalizedSource(
        raw_bytes=raw_bytes,
        decoded_content=decoded,
        normalized_content=normalized,
        raw_hash=sha256(raw_bytes),
        normalized_hash=sha256(normalized.encode("utf-8")),
        normalized_origin=normalize_origin(origin),
        extracted_metadata=metadata,
    )
