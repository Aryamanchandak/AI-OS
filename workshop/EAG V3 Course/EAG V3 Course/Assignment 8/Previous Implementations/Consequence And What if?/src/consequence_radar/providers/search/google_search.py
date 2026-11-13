from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ...config import Settings
from ...metering import UsageLedger


@dataclass(frozen=True)
class SearchResult:
    url: str
    title: str
    snippet: str = ""


class SearchProvider(Protocol):
    def search(self, query: str, *, max_results: int) -> list[SearchResult]: ...


class GeminiGoogleSearchProvider:
    """Google Search grounding adapter; model name remains configuration-owned."""

    def __init__(self, settings: Settings, ledger: UsageLedger, on_call=None, run_id_getter=None):
        if not settings.api_key:
            raise RuntimeError("GEMINI_API_KEY or GOOGLE_API_KEY is required for grounded search")
        from google import genai
        self.settings, self.ledger, self.on_call, self.run_id_getter = settings, ledger, on_call, run_id_getter
        self.client = genai.Client(api_key=settings.api_key)

    def search(self, query: str, *, max_results: int) -> list[SearchResult]:
        from google.genai import types
        self.ledger.guard_external_call("search")
        tools = [types.Tool(google_search=types.GoogleSearch())]
        if self.settings.enable_url_context_search:
            # Combined with Grounding with Search, this lets the model open
            # each candidate result and ground its relevance description in
            # the page itself, not just the search snippet. Tool use is
            # incompatible with response_json_schema (confirmed against the
            # live API), so this call stays hand-parsed plain text, same as
            # before -- it never becomes structured output.
            tools.append(types.Tool(url_context=types.UrlContext()))
        response = self.client.models.generate_content(model=self.settings.fast_model, contents=f"Find up to {max_results} sources for this research query and briefly describe relevance: {query}", config=types.GenerateContentConfig(tools=tools, automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True)))
        usage = getattr(response, "usage_metadata", None)
        prompt_tokens = int(getattr(usage, "prompt_token_count", 0) or 0)
        # URL-context-retrieved content is billed separately from the prompt
        # itself; fold it into input-token accounting so the cost ledger
        # reflects what the call actually cost.
        tool_use_tokens = int(getattr(usage, "tool_use_prompt_token_count", 0) or 0)
        output_tokens = int(getattr(usage, "candidates_token_count", 0) or 0)
        input_tokens = prompt_tokens + tool_use_tokens
        self.ledger.record(input_tokens, output_tokens)
        if self.on_call:
            self.on_call({"run_id": self.run_id_getter() if self.run_id_getter else "", "stage": "grounded_search", "model_name": self.settings.fast_model, "prompt_version": "google-search-1", "input_tokens": input_tokens, "output_tokens": output_tokens, "tool_use_prompt_token_count": tool_use_tokens, "retry_count": 0})
        results: list[SearchResult] = []
        for candidate in response.candidates or []:
            metadata = getattr(candidate, "grounding_metadata", None)
            chunks = getattr(metadata, "grounding_chunks", None) or []
            # grounding_supports carries the model's relevance text for each
            # chunk it cited, indexed by grounding_chunk_indices; join the
            # segments naming a given chunk into that source's snippet.
            snippets_by_chunk: dict[int, list[str]] = {}
            for support in getattr(metadata, "grounding_supports", None) or []:
                text = getattr(getattr(support, "segment", None), "text", None)
                if not text:
                    continue
                for index in getattr(support, "grounding_chunk_indices", None) or []:
                    snippets_by_chunk.setdefault(index, []).append(text)
            for index, chunk in enumerate(chunks):
                web = getattr(chunk, "web", None)
                if web and getattr(web, "uri", None):
                    snippet = " ".join(snippets_by_chunk.get(index, []))
                    results.append(SearchResult(str(web.uri), str(getattr(web, "title", "") or web.uri), snippet))
        seen, unique = set(), []
        for result in results:
            if result.url not in seen:
                seen.add(result.url); unique.append(result)
        return unique[:max_results]
