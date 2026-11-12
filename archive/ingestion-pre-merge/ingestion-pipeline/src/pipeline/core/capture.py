from __future__ import annotations
import os
from datetime import datetime, timezone
from pydantic import BaseModel
from .config import RAW_DATA_ROOT
from .ids import content_hash, mint_item_id
from .ledger import Item, get_item, register_item
from .paths import bronze_dir


class CaptureResult(BaseModel):
    duplicate: bool
    content_hash: str
    item_id: str
    path: str | None = None


def capture(source: str, content: str, metadata: dict | None = None, authored: bool = False) -> CaptureResult:
    h = content_hash(content)
    existing = get_item(h)
    if existing:
        return CaptureResult(duplicate=True, content_hash=h, item_id=existing.item_id)

    item_id = mint_item_id(source)
    directory = bronze_dir(source)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{item_id}.md"
    now = datetime.now(timezone.utc).isoformat()

    meta = metadata or {}
    frontmatter = [
        "---",
        f"item_id: {item_id}",
        f"source: {source}",
        f"content_hash: {h}",
        f"captured_at: {now}",
        f"authored: {str(authored).lower()}",
    ]
    for key, value in meta.items():
        frontmatter.append(f"{key}: {value}")
    frontmatter.extend(["---", ""])
    path.write_text("\n".join(frontmatter) + content, encoding="utf-8")
    os.chmod(path, 0o444)

    rel = str(path.relative_to(RAW_DATA_ROOT))
    register_item(Item(h, item_id, source, now, rel, authored, meta))
    return CaptureResult(duplicate=False, content_hash=h, item_id=item_id, path=str(path))
