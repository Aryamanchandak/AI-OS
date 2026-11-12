# advisor-gateway

`advisor-gateway` is a dependency-free Python 3.11 gateway loop in which an inexpensive
executor can privately consult a stronger model and then finish the response itself. Both
models are accessed through non-streaming OpenAI-compatible Chat Completions endpoints.

## Setup

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
advisor-gateway --help
```

## Run a local executor with a remote advisor

The executor URL defaults to Ollama's OpenAI-compatible endpoint at
`http://127.0.0.1:11434/v1`. Model names and the advisor base URL are required.

```bash
export ADVISOR_GATEWAY_EXECUTOR_MODEL="gemma3"
export ADVISOR_GATEWAY_ADVISOR_BASE_URL="https://api.example.com/v1"
export ADVISOR_GATEWAY_ADVISOR_MODEL="strong-model"
export ADVISOR_GATEWAY_ADVISOR_API_KEY="your-secret-key"

advisor-gateway run --prompt "Review this migration plan and produce the final answer."
printf '%s\n' "Explain the failure in this log." | advisor-gateway run
```

Every setting also has a flag: `--executor-base-url`, `--advisor-base-url`,
`--executor-model`, `--advisor-model`, `--executor-api-key`, `--advisor-api-key`,
`--max-uses`, `--max-tokens`, `--dummy-input-field`, `--usage-db`, and `--timeout`.
Use `--dummy-input-field placeholder` for servers that reject a zero-property tool schema.
Use `--json` for the canonical response plus per-inference usage; otherwise only final text is
written to stdout. Diagnostics go to stderr and never include API keys or provider bodies.

## Privacy warning

Each advisor consultation sends the executor's full working transcript to the advisor endpoint:
the system prompt, tool definitions, prior messages, tool results, and partial current response.
Do not use a remote advisor for secrets, personal data, proprietary tool output, or other material
that its operator is not permitted to receive. The gateway does not redact or classify content.

## Current limitations

- Non-streaming Chat Completions only; this package is a CLI/library, not an HTTP proxy server.
- OpenAI-compatible function tools must use JSON-object arguments.
- Mixed advisor and client-owned tool calls are returned unchanged for the embedding client.
- There is no retry, prompt caching transport support, automatic redaction, or production eval corpus.
- Compatibility varies across local servers; zero-property tool support should be tested per runtime.

Optional `--usage-db PATH` records one SQLite row for every executor and advisor inference. It
stores model names and token counts, but not prompts, responses, or API keys.
