"""Primary-source retrieval: PubMed E-utilities and arXiv.

Both are free and keyless. This module is the `fetch` skill — it is
deliberately deterministic code rather than an LLM call, because the one
thing an evidence pipeline must never do is invent a citation.
"""

from __future__ import annotations

import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, asdict, field
from typing import Any

_UA = {"User-Agent": "veritas-claim-verifier/1.0 (educational; EAG V3 Assignment 5)"}
_TIMEOUT = 25


@dataclass
class Source:
    id: str = ""
    title: str = ""
    abstract: str = ""
    authors: list[str] = field(default_factory=list)
    year: str = ""
    venue: str = ""
    doi: str = ""
    url: str = ""
    db: str = ""
    query: str = ""
    stance: str = ""
    sub_claim_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as fh:
        return fh.read()


def _text(node, path: str, default: str = "") -> str:
    found = node.find(path)
    return (found.text or default).strip() if found is not None and found.text else default


# --------------------------------------------------------------------------- #
# PubMed
# --------------------------------------------------------------------------- #

def search_pubmed(query: str, limit: int) -> list[Source]:
    base = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
    params = urllib.parse.urlencode(
        {"db": "pubmed", "term": query, "retmax": limit, "retmode": "json", "sort": "relevance"}
    )
    try:
        import json as _json

        ids = _json.loads(_get(f"{base}/esearch.fcgi?{params}"))["esearchresult"]["idlist"]
    except Exception:
        return []
    if not ids:
        return []

    fetch_params = urllib.parse.urlencode(
        {"db": "pubmed", "id": ",".join(ids), "retmode": "xml"}
    )
    try:
        root = ET.fromstring(_get(f"{base}/efetch.fcgi?{fetch_params}"))
    except Exception:
        return []

    out: list[Source] = []
    for art in root.findall(".//PubmedArticle"):
        pmid = _text(art, ".//PMID")
        # Abstracts are split across labelled sections; join them in order.
        chunks = []
        for seg in art.findall(".//Abstract/AbstractText"):
            label = seg.get("Label")
            body = "".join(seg.itertext()).strip()
            chunks.append(f"{label}: {body}" if label else body)
        out.append(
            Source(
                id=f"PMID:{pmid}",
                title=" ".join("".join(t.itertext()) for t in art.findall(".//ArticleTitle")),
                abstract=" ".join(chunks),
                authors=[
                    f"{_text(a, 'LastName')} {_text(a, 'Initials')}".strip()
                    for a in art.findall(".//Author")[:6]
                ],
                year=_text(art, ".//PubDate/Year") or _text(art, ".//PubDate/MedlineDate")[:4],
                venue=_text(art, ".//Journal/Title"),
                doi=next(
                    (i.text or "" for i in art.findall(".//ArticleId")
                     if i.get("IdType") == "doi"),
                    "",
                ),
                url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                db="pubmed",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# arXiv
# --------------------------------------------------------------------------- #

_ATOM = "{http://www.w3.org/2005/Atom}"


def search_arxiv(query: str, limit: int) -> list[Source]:
    params = urllib.parse.urlencode(
        {"search_query": f"all:{query}", "start": 0, "max_results": limit,
         "sortBy": "relevance"}
    )
    try:
        root = ET.fromstring(_get(f"http://export.arxiv.org/api/query?{params}"))
    except Exception:
        return []

    out: list[Source] = []
    for entry in root.findall(f"{_ATOM}entry"):
        raw_id = _text(entry, f"{_ATOM}id")
        arxiv_id = raw_id.rsplit("/", 1)[-1]
        out.append(
            Source(
                id=f"arXiv:{arxiv_id}",
                title=" ".join(_text(entry, f"{_ATOM}title").split()),
                abstract=" ".join(_text(entry, f"{_ATOM}summary").split()),
                authors=[
                    _text(a, f"{_ATOM}name")
                    for a in entry.findall(f"{_ATOM}author")[:6]
                ],
                year=_text(entry, f"{_ATOM}published")[:4],
                venue="arXiv (preprint)",
                url=raw_id,
                db="arxiv",
            )
        )
    return out


# --------------------------------------------------------------------------- #
# fetch skill entry point
# --------------------------------------------------------------------------- #

def fetch_all(
    queries: list[dict[str, Any]],
    cfg: dict[str, Any],
    seen: set[str] | None = None,
    log=lambda *_: None,
) -> tuple[list[Source], set[str]]:
    """Run every query against enabled databases; dedupe by source id.

    `seen` carries ids from earlier rounds so a retry does not re-surface the
    same papers the verifier already judged insufficient.
    """
    seen = set(seen or ())
    per_query = cfg["pipeline"]["max_sources_per_query"]
    cap = cfg["pipeline"]["max_total_sources"]
    collected: list[Source] = []

    for q in queries:
        if len(collected) >= cap:
            break
        text = q.get("query", "").strip()
        if not text:
            continue

        hits: list[Source] = []
        if cfg["sources"]["pubmed"]["enabled"]:
            hits += search_pubmed(text, per_query)
        if cfg["sources"]["arxiv"]["enabled"]:
            hits += search_arxiv(text, per_query)
        time.sleep(0.35)  # be polite to NCBI

        fresh = 0
        for s in hits:
            if s.id in seen or not s.abstract:
                continue
            seen.add(s.id)
            s.query, s.stance = text, q.get("stance", "")
            s.sub_claim_id = q.get("sub_claim_id", "")
            collected.append(s)
            fresh += 1
            if len(collected) >= cap:
                break
        log(f"    [{q.get('stance','?'):>13}] {text[:52]:<52} -> {fresh} new")

    return collected, seen
