"""Shared deterministic-ID helpers (PLAN Phase 2 — retry safety).

One fixed UUID namespace for every deterministic id the ingestion pipeline
mints, so the *same input always yields the same id* across runs, processes, and
stores (KG, content SQLite, vector). A retry recomputes the id instead of
minting a new random one — that is the whole point of using deterministic ids
rather than uuid4 (see PLAN_PART1 §6.2).

The namespace value is historical: it was the KG consumer's private
`_NAMESPACE`, promoted here unchanged so every previously-minted id (highlight,
edge, claim, identity proposal) is byte-for-byte stable.
"""

from __future__ import annotations

import uuid

from gateway.ingestion.kg.identity import normalize_label

# Fixed namespace so ids are stable across runs/processes for the same input.
NAMESPACE = uuid.UUID("6f6d6167-6572-4b47-8000-000000000001")


def deterministic_id(*parts: str) -> str:
    """Return a stable UUID5 string derived from the given key parts."""
    return str(uuid.uuid5(NAMESPACE, ":".join(parts)))


def highlight_id_for_highlight(source_record_id: str, highlight_index: int) -> str:
    """Deterministic id for one parsed highlight (T33).

    A document is split into ordered highlights by the parse step
    (`ingestion.parsing`) and each one gets its own envelope, so a highlight is
    identified by its parent document plus its position in that document. The
    index is the ledger's stored `highlights.highlight_index`, never recomputed
    by re-splitting — the segmenter is model-backed and its boundaries are not
    reproducible across runs.

    This is the real Highlight id, not a stand-in: it keys the KG's
    `contributing_highlight_ids`, the content store's `highlight` table, and
    the vector projection's `highlight_id` metadata. The format must not change
    or existing rows in all three stop lining up.
    """
    if highlight_index < 0:
        raise ValueError("highlight_index must be >= 0")
    return str(uuid.uuid5(NAMESPACE, f"highlight:{source_record_id}:{highlight_index}"))


def concept_id_for(label: str, domain: str) -> str:
    """Domain-scoped deterministic concept id (PLAN Phase 2 / decision 4).

    Identity key is ``normalized_label | normalized_domain``:

    - same label + same domain  -> same id, across every source
    - different domain          -> different id (duration/economics != duration/physics)

    This replaces the old random uuid4 for new concepts so a retry lands on the
    same node. It does NOT decide semantic identity beyond the domain scope;
    fuzzy synonym-merging stays a reviewed step (T22).
    """
    key = f"concept:{normalize_label(label)}|{normalize_label(domain)}"
    return str(uuid.uuid5(NAMESPACE, key))
