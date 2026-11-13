"""Build and index the corpus the RAG application answers from.

    uv run python build_corpus.py download   # fetch each topic into sandbox/corpus/
    uv run python build_corpus.py index      # chunk + embed every file (needs a key)
    uv run python build_corpus.py index path/to/folder   # index your own .md/.txt files

`download` reads corpus/topics.txt (one Wikipedia article title per line),
saves each article's plain text as a markdown file, and writes
corpus/manifest.csv. `index` sends every file through the same
`index_document` tool the agent uses, so the corpus and the agent share one
index.
"""

from __future__ import annotations

import csv
import re
import shutil
import sys
import time
from pathlib import Path

import httpx

from paths import ROOT

TOPICS = ROOT / "corpus" / "topics.txt"
MANIFEST = ROOT / "corpus" / "manifest.csv"
CORPUS_DIR = ROOT / "sandbox" / "corpus"
API = "https://en.wikipedia.org/w/api.php"
HEADERS = {"User-Agent": "a07-rag/0.1 (course assignment)"}
MAX_WORDS = 3000  # keep each item to a handful of chunks
PAUSE_SECONDS = 10  # be polite to Wikipedia; it rate-limits fast callers


def slug(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


def trim(text: str, max_words: int = MAX_WORDS) -> str:
    words = text.split()
    return " ".join(words[:max_words])


def fetch_article(client: httpx.Client, title: str) -> tuple[str, str, str]:
    """(resolved title, url, plain text) for one Wikipedia article."""
    r = client.get(API, params={
        "action": "query", "prop": "extracts|info", "explaintext": 1, "redirects": 1,
        "inprop": "url", "titles": title, "format": "json", "formatversion": 2,
    })
    r.raise_for_status()
    page = r.json()["query"]["pages"][0]
    if page.get("missing") or not page.get("extract"):
        raise LookupError(f"No article text for {title!r}")
    return page["title"], page["fullurl"], page["extract"]


def download() -> int:
    CORPUS_DIR.mkdir(parents=True, exist_ok=True)
    titles = [t.strip() for t in TOPICS.read_text().splitlines() if t.strip()]
    rows = []
    with httpx.Client(headers=HEADERS, timeout=30, follow_redirects=True) as client:
        for title in titles:
            path = CORPUS_DIR / f"{slug(title)}.md"
            if path.exists():  # already downloaded: read its header, skip the network
                lines = path.read_text(encoding="utf-8").splitlines()
                resolved, url = lines[0].removeprefix("# "), lines[2].removeprefix("Source: ")
                body = " ".join(lines[4:])
            else:
                resolved, url, text = fetch_article(client, title)
                body = trim(text)
                path.write_text(f"# {resolved}\n\nSource: {url}\n\n{body}\n", encoding="utf-8")
                print(f"saved {path.name} ({len(body.split())} words)")
                time.sleep(PAUSE_SECONDS)
            rows.append({
                "file": f"corpus/{path.name}", "title": resolved, "url": url,
                "words": len(body.split()), "licence": "CC BY-SA 4.0 (Wikipedia)",
            })
    with open(MANIFEST, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"{len(rows)} items; manifest at {MANIFEST}")
    return len(rows)


def index(folder: Path | None = None) -> int:
    import mcp_server  # imported here so `download` needs no model key

    if folder is not None:  # copy the user's own files into the sandbox first
        target = ROOT / "sandbox" / "own"
        target.mkdir(parents=True, exist_ok=True)
        for src in sorted(folder.rglob("*")):
            if src.suffix.lower() in {".md", ".txt"}:
                shutil.copy(src, target / src.name)
        files = sorted(target.iterdir())
    else:
        files = sorted(CORPUS_DIR.glob("*.md"))
    total = 0
    for path in files:
        rel = path.relative_to(ROOT / "sandbox")
        report = mcp_server.index_document(str(rel))
        total += report["chunks_indexed"]
        print(f"indexed {rel}: {report['chunks_indexed']} chunks")
    print(f"{len(files)} files, {total} chunks")
    return total


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command == "download":
        download()
    elif command == "index":
        index(Path(sys.argv[2]) if len(sys.argv) > 2 else None)
    else:
        sys.exit(__doc__)
