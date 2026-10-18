# Local Ollama adapter

This folder adapts local Ollama models to the gateway's chat, vision, tool, structured-output, and embedding interfaces.

| File | Responsibility |
| --- | --- |
| `__init__.py` | Implements `OllamaProvider`: builds `/api/chat` and `/api/embed` requests, translates images and conversation history, and normalizes results/usage. |
| `tools.py` | Uses model-name hints to select native tool support; otherwise describes tools in the system prompt and parses a returned JSON tool call. |

Configured local models come from `local_models.yaml`; `OLLAMA_URL` controls the server address. Configuration supplies model pins, context windows, vision flags, and whether `think: false` must be sent. Image data moves into Ollama's sibling `images` array. Structured output maps to the `format` field.

Models with native tool support receive function definitions. Other models receive prompted tool instructions, with tool results translated to user text. The adapter reports the selected tool dialect in its normalized result. It does not execute tools itself.

`chat()` requests `stream: false`; `stream()` yields the completed chat through the buffered fallback. `embed()` reads vectors from Ollama's embedding response. Cross-provider retry and spending policy live in [orchestration](../../orchestration/README.md), rather than in this adapter.
