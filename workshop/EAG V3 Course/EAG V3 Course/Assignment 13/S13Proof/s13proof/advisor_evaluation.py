"""Measure complete supporting passages against a fixed 40-word retrieval control."""
from __future__ import annotations

import csv
import hashlib
import json
import re
from pathlib import Path

from s13code.core.memory import MemoryKind, MemoryRecord, MemoryScope, MemoryStore, Principal, SourceRef
from s13code.core.memory.chunking import fixed_word_chunks, prepare_markdown, semantic_chunks
from s13code.core.memory.embeddings import DeterministicEmbedder

COURSE = Path(__file__).resolve().parents[2] / "S13Code-2" / "sandbox"
SCOPE = MemoryScope("synthetic-eval", "papers", "student")


def normalized(text):
    return " ".join(text.split())


def evaluate() -> dict:
    embedder = DeterministicEmbedder(256)
    semantic = MemoryStore(embedder=embedder)
    fixed = MemoryStore(embedder=embedder)
    hashes, documents, prepared_sources = {}, [], {}
    try:
        for source in sorted((COURSE / "papers").glob("*.txt")):
            raw = source.read_text()
            hashes[source.name] = hashlib.sha256(raw.encode()).hexdigest()
            prepared, preprocessing = prepare_markdown(raw)
            prepared_sources[source.name] = prepared
            chunks = semantic_chunks(prepared, embedder, preprocess=False)
            kwargs = dict(source_text=raw, prepared_text=prepared, chunks=chunks,
                          source_uri=f"fixture://papers/{source.name}", scope=SCOPE,
                          source_author="synthetic-indexer", preprocessing=preprocessing)
            first = semantic.ingest_document(**kwargs)
            again = semantic.ingest_document(**kwargs)
            covered = all(sum(chunk.source_start_char <= word.start() and word.end() <= chunk.source_end_char
                              for chunk in chunks) == 1 for word in re.finditer(r"\S+", prepared))
            exact = all(prepared[chunk.source_start_char:chunk.source_end_char].strip() == chunk.text
                        for chunk in chunks)
            documents.append({"source": source.name, "coverage_exact": covered and exact,
                              "reindex_idempotent": again["idempotent"] and
                              first["record_ids"] == again["record_ids"]})
            for text in fixed_word_chunks(prepared, words=40):
                fixed.write(MemoryRecord(MemoryKind.DOCUMENT_CHUNK, SCOPE, text,
                    [SourceRef(f"fixture://papers/{source.name}", "synthetic-indexer")],
                    Principal("synthetic-indexer", "agent")))
        with (COURSE / "advisor_cases.csv").open() as case_file:
            cases = list(csv.DictReader(case_file))
        rows, totals = [], {name: {"source_at_3": 0, "complete_evidence_at_3": 0, "retrieved_words": 0}
                            for name in ("semantic", "fixed_40_words")}
        for case in cases:
            expected = f"fixture://papers/{case['source']}"
            label_present = normalized(case["quote"]) in normalized(prepared_sources[case["source"]])
            if not label_present:
                raise ValueError(f"label absent from source: {case['id']}")
            row = {"id": case["id"], "query": case["query"], "label_present": label_present}
            for name, store in (("semantic", semantic), ("fixed_40_words", fixed)):
                hits = store.recall(case["query"], SCOPE, kinds=[MemoryKind.DOCUMENT_CHUNK], limit=3)
                source_hit = any(hit.sources[0].uri == expected for hit in hits)
                complete = any(hit.sources[0].uri == expected and
                               normalized(case["quote"]) in normalized(hit.text) for hit in hits)
                words = sum(len(hit.text.split()) for hit in hits)
                totals[name]["source_at_3"] += int(source_hit)
                totals[name]["complete_evidence_at_3"] += int(complete)
                totals[name]["retrieved_words"] += words
                row[name] = {"source_found": source_hit, "complete_evidence": complete,
                             "retrieved_words": words}
            rows.append(row)
        for total in totals.values():
            total["mean_retrieved_words"] = round(total.pop("retrieved_words") / len(cases), 1)
        return {"mode": "offline-heading-segmentation-and-deterministic-embeddings", "queries": len(cases),
                "corpus_sha256": hashes, "documents": documents, "cases": rows, **totals,
                "limitation": "Longer chunks expose more words. This measures complete evidence at k=3, "
                              "not equal-token efficiency, live Nomic quality, or advisor judgment accuracy."}
    finally:
        semantic.close()
        fixed.close()


if __name__ == "__main__":
    print(json.dumps(evaluate(), indent=2))
