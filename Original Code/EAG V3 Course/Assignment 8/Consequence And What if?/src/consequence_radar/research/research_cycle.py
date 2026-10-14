from __future__ import annotations

import json
from urllib.parse import urlsplit

from ..config import Settings
from ..evidence import verify_claims
from ..models import CausalGraph, EvidenceClaimDrafts, ResearchTask, ResearchTaskList, SourceRecord
from ..providers.fetch import PageFetcher, normalize_url
from ..providers.model import ModelClient
from ..providers.search import SearchProvider


def generate_tasks(run_id: str, graph: CausalGraph, model: ModelClient, settings: Settings) -> list[ResearchTask]:
    result = model.generate(run_id=run_id, stage="gap_analysis", prompt_name="research/gap_analyser.md", prompt_data=graph.model_dump_json(), schema=ResearchTaskList)
    priority = {"high": 0, "medium": 1, "low": 2}
    return sorted(result.tasks, key=lambda t: priority[t.priority])[:settings.max_research_tasks_per_cycle]


def retrieve_for_tasks(tasks: list[ResearchTask], search: SearchProvider, fetcher: PageFetcher, settings: Settings, counters: dict[str, int], guard=lambda: None) -> tuple[list[SourceRecord], list[str]]:
    sources, failures, seen = [], [], set()
    for task in tasks:
        for query in task.search_queries:
            guard()
            if counters["queries"] >= settings.max_search_queries_per_run: break
            counters["queries"] += 1
            try: results = search.search(query, max_results=5)
            except Exception as exc: failures.append(f"{query}: {exc}"); continue
            for hit in results:
                guard()
                if counters["sources"] >= settings.max_fetched_sources_per_run: break
                try: canonical = normalize_url(hit.url)
                except Exception as exc: failures.append(f"{hit.url}: {exc}"); continue
                if canonical in seen: continue
                seen.add(canonical); counters["sources"] += 1
                try:
                    fetched = fetcher.fetch(canonical)
                    sources.append(SourceRecord(id=f"S{counters['sources']}", url=fetched.final_url, title=fetched.title or hit.title, publisher=urlsplit(fetched.final_url).hostname or "", retrieved_at=fetched.retrieved_at, extracted_text=fetched.text, content_type=fetched.content_type, suitability_reason=f"Retrieved for task {task.id}: {task.question}"))
                except Exception as exc: failures.append(f"{canonical}: {exc}")
    return sources, failures


def extract_claims(run_id: str, tasks: list[ResearchTask], sources: list[SourceRecord], model: ModelClient, start: int = 1):
    payload = json.dumps({"tasks": [t.model_dump(mode="json") for t in tasks], "sources": [{**s.model_dump(mode="json"), "extracted_text": s.extracted_text[:8000]} for s in sources]}, ensure_ascii=False)
    drafts = model.generate(run_id=run_id, stage="claim_extraction", prompt_name="research/claim_extractor.md", prompt_data=payload, schema=EvidenceClaimDrafts)
    return verify_claims(drafts.claims, sources, start)
