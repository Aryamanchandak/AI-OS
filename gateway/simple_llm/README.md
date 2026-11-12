# Simple LLM

Independent Python client: keys in `.env`, direct calls to OpenAI, Anthropic
or Ollama. No server, gateway imports, database, budgets or cost tracking.
This whole folder can be copied into another project.

Requires Python 3.11 or newer. From this folder:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env
```

Fill in the keys you use. `.env` is ignored by Git. Shell variables take
precedence. For Ollama, start it and download the chosen local models.

From Python in the parent directory (or your project after copying the folder):

```python
from simple_llm import LLM

with LLM() as llm:
    reply = llm.chat("Reply with exactly OK", provider="anthropic")
    print(reply["text"])

    reply = llm.chat("Summarize this text: ...", provider="openai")
    print(reply["text"])

    result = llm.embed("Text to index")  # local nomic-embed-text
    vector = result["embedding"]
```

Use the environment where you installed the requirements. You can also import
`LLM` from `client` when running directly inside this folder.

For ingestion, reuse one `LLM` instance. `chat` also accepts `messages`, `system`,
`model`, `max_tokens`, and optional `temperature`. These are synchronous calls;
inside async code use `await asyncio.to_thread(llm.chat, ...)`.

For structured extraction:

```python
schema = {
    "type": "object",
    "properties": {"summary": {"type": "string"}},
    "required": ["summary"],
    "additionalProperties": False,
}
with LLM() as llm:
    result = llm.chat("Summarize: ...", schema=schema)
    print(result["parsed"]["summary"])
```

The selected model must support the requested features. Provider errors and
invalid JSON raise exceptions. SDKs retry transient failures twice. Calls may
incur provider charges. Embedding model and dimension must match your existing
collection; do not mix vectors from different models.

This is ready to import; it does not automatically replace ingestion's existing
gateway client. It has no gateway profiles: select provider/model explicitly.

Verification (from the parent directory, with pytest installed):

```bash
python -m pytest simple_llm/tests -q
```

Tests use mock HTTP responses. Live calls need your keys and running local models.
