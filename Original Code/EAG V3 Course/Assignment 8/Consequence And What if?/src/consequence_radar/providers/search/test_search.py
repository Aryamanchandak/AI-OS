from types import SimpleNamespace

from consequence_radar.providers.search import GeminiGoogleSearchProvider


class StubLedger:
    def __init__(self):
        self.recorded = None
        self.guarded = []

    def guard_external_call(self, kind="model"):
        self.guarded.append(kind)

    def record(self, input_tokens, output_tokens):
        self.recorded = (input_tokens, output_tokens)


def web_chunk(uri, title):
    return SimpleNamespace(web=SimpleNamespace(uri=uri, title=title))


def support(text, *chunk_indices):
    return SimpleNamespace(segment=SimpleNamespace(text=text), grounding_chunk_indices=list(chunk_indices))


def response(chunks, supports, *, prompt_tokens=25, tool_use_tokens=105, output_tokens=452):
    metadata = SimpleNamespace(grounding_chunks=chunks, grounding_supports=supports)
    return SimpleNamespace(
        candidates=[SimpleNamespace(grounding_metadata=metadata)],
        usage_metadata=SimpleNamespace(
            prompt_token_count=prompt_tokens,
            tool_use_prompt_token_count=tool_use_tokens,
            candidates_token_count=output_tokens,
        ),
    )


class StubModels:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def generate_content(self, *, model, contents, config):
        self.calls.append(SimpleNamespace(model=model, contents=contents, config=config))
        return self.response

    @property
    def config(self):
        return self.calls[-1].config


def make_provider(models, ledger, on_call=None, enable_url_context_search=True):
    provider = object.__new__(GeminiGoogleSearchProvider)
    provider.settings = SimpleNamespace(fast_model="gemini-test", enable_url_context_search=enable_url_context_search)
    provider.ledger = ledger
    provider.on_call = on_call
    provider.run_id_getter = None
    provider.client = SimpleNamespace(models=models)
    return provider


def test_search_includes_both_tools_and_populates_real_snippets():
    chunks = [web_chunk("https://ijirt.org/a", "ijirt.org"), web_chunk("https://upstox.com/b", "upstox.com")]
    supports = [
        support("This paper examines repo rate effects on bank stocks.", 0),
        support("It concludes a nuanced medium-term relationship.", 0),
        support("This article covers sector-wide RBI policy impact.", 1),
    ]
    models = StubModels(response(chunks, supports))
    provider = make_provider(models, StubLedger())

    results = provider.search("RBI repo rate impact", max_results=5)

    tools_dump = [t.model_dump(exclude_none=True) for t in models.config.tools]
    assert any("google_search" in t for t in tools_dump)
    assert any("url_context" in t for t in tools_dump)

    assert len(results) == 2
    assert results[0].url == "https://ijirt.org/a"
    assert results[0].snippet == "This paper examines repo rate effects on bank stocks. It concludes a nuanced medium-term relationship."
    assert results[1].snippet == "This article covers sector-wide RBI policy impact."


def test_url_context_tool_omitted_when_disabled():
    models = StubModels(response([], []))
    provider = make_provider(models, StubLedger(), enable_url_context_search=False)

    provider.search("query", max_results=5)

    tools_dump = [t.model_dump(exclude_none=True) for t in models.config.tools]
    assert all("url_context" not in t for t in tools_dump)
    assert any("google_search" in t for t in tools_dump)


def test_chunk_without_matching_support_gets_empty_snippet():
    chunks = [web_chunk("https://example.com", "example.com")]
    models = StubModels(response(chunks, []))
    provider = make_provider(models, StubLedger())

    results = provider.search("query", max_results=5)

    assert results[0].snippet == ""


def test_usage_ledger_and_audit_include_tool_use_tokens():
    chunks = [web_chunk("https://example.com", "example.com")]
    calls = []
    models = StubModels(response(chunks, [], prompt_tokens=25, tool_use_tokens=105, output_tokens=452))
    provider = make_provider(models, StubLedger(), on_call=calls.append)

    provider.search("query", max_results=5)

    assert provider.ledger.recorded == (25 + 105, 452)
    assert calls[0]["input_tokens"] == 130
    assert calls[0]["tool_use_prompt_token_count"] == 105
    assert calls[0]["output_tokens"] == 452


def test_missing_tool_use_prompt_token_count_defaults_to_zero():
    chunks = [web_chunk("https://example.com", "example.com")]
    usage = SimpleNamespace(prompt_token_count=10, candidates_token_count=5)
    resp = SimpleNamespace(candidates=[SimpleNamespace(grounding_metadata=SimpleNamespace(grounding_chunks=chunks, grounding_supports=[]))], usage_metadata=usage)
    models = StubModels(resp)
    provider = make_provider(models, StubLedger())

    provider.search("query", max_results=5)

    assert provider.ledger.recorded == (10, 5)


def test_results_are_deduplicated_and_capped():
    chunks = [web_chunk("https://a.com", "a"), web_chunk("https://a.com", "a-dup"), web_chunk("https://b.com", "b")]
    models = StubModels(response(chunks, []))
    provider = make_provider(models, StubLedger())

    results = provider.search("query", max_results=1)

    assert len(results) == 1
    assert results[0].url == "https://a.com"
