"""Per-book markdown export (spec §9), flushed immediately on each accept.

Each page is one block delimited by HTML-comment markers keyed by page_id, so a
re-save (cockpit back-nav) rewrites that page's block in place instead of
appending a duplicate. edited_text is the only non-regenerable data, so this is
the durability backstop — the DB is disposable, data/output/ is not.
"""

from __future__ import annotations

import csv
import re
import sqlite3
from pathlib import Path


def _block(page_id: int, passages: list[dict], page_number: int | None) -> str:
    """Render one page's block: marker, blockquotes, marker. Empty passages skip."""
    lines = [f"<!-- page:{page_id} -->"]
    for p in passages:
        text = (p.get("edited_text") or "").strip()
        if not text:
            continue                      # cleared junk field → emit nothing
        lines.append(f"> {text}")
        if page_number is not None:
            lines.append(f"— p.{page_number}")
        lines.append("")                  # blank line between passages
    lines.append(f"<!-- /page:{page_id} -->")
    return "\n".join(lines)


def _header(batch: str, author: str | None) -> str:
    h = f"# {batch}\n"
    if author:
        h += f"*{author}*\n"
    return h


def append_or_update_page(
    page_id: int,
    batch: str,
    author: str | None,
    passages: list[dict],
    page_number: int | None,
    output_dir: str | Path,
) -> Path:
    """Write/replace this page's block in data/output/<batch>.md."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{batch}.md"

    block = _block(page_id, passages, page_number)

    if not path.exists():
        content = _header(batch, author) + "\n" + block + "\n"
        path.write_text(content, encoding="utf-8")
        return path

    content = path.read_text(encoding="utf-8")

    # Refresh the header on every save so an author added mid-batch appears immediately.
    first_block = content.find("<!-- page:")
    if first_block == -1:
        # File exists but has no page blocks yet; rewrite header + this block.
        path.write_text(_header(batch, author) + "\n" + block + "\n", encoding="utf-8")
        return path
    content = _header(batch, author) + "\n" + content[first_block:]

    marker = re.compile(
        rf"<!-- page:{page_id} -->.*?<!-- /page:{page_id} -->",
        re.DOTALL,
    )
    if marker.search(content):
        content = marker.sub(lambda _m: block, content)
    else:
        content = content.rstrip() + "\n\n" + block + "\n"
    path.write_text(content, encoding="utf-8")
    return path


def export_readwise_csv(
    db_path: str | Path,
    batch: str,
    output_dir: str | Path,
) -> Path | None:
    """Write a Readwise bulk-import CSV for all reviewed passages in a batch.

    Columns: Highlight, Title, Author, Note, Location
    Returns the Path written, or None if no reviewed passages exist.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT pg.batch, pg.author, pg.page_number, ps.edited_text
          FROM passages ps
          JOIN pages pg ON ps.page_id = pg.id
         WHERE pg.batch = ?
           AND pg.status = 'reviewed'
         ORDER BY pg.id, ps.id
        """,
        (batch,),
    ).fetchall()
    conn.close()

    passages = [
        r for r in rows if (r["edited_text"] or "").strip()
    ]
    if not passages:
        return None

    path = output_dir / f"{batch}.csv"
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f, quoting=csv.QUOTE_ALL)
        writer.writerow(["Highlight", "Title", "Author", "Note", "Location"])
        for r in passages:
            writer.writerow([
                r["edited_text"].strip(),
                r["batch"],
                r["author"] or "",
                "",
                r["page_number"] if r["page_number"] is not None else "",
            ])
    return path
