"""Per-model capability resolution.

`/api/llm/capabilities` reports what a provider *instance* can do, and that is
model-dependent: the same package answers differently for `gemini-2.5-flash`
and `gemini-2.5-flash-lite`. Ported from `model_capabilities()` in
`glc_v5/glc/providers.py:1253`.

In the legacy tree this also fed `Router.pick()`. Routing is dormant here
(decision #6), so this feeds reporting only — nothing in candidate selection
reads it.
"""

from __future__ import annotations

from gateway.llm.providers.base import ProviderCapabilities

#: Model families that accept a reasoning/thinking dial on an OpenAI-compatible
#: surface. From `REASONING_MODEL_HINTS` in `glc_v5/glc/providers.py:262`.
REASONING_MODEL_HINTS = (
    "gpt-oss", "qwen3-think", "deepseek-r1", "deepseek-r2", "qwen3",
    "o1", "o3", "o4", "gpt-5", "glm", "nemotron", "deepseek-v3.2", "deepseek-v4",
)

#: Families whose thinking channel is ON unless told otherwise — an `off` that
#: emits no field at all cannot stop them, so "off" has to be stated in the
#: dialect the server understands. From `THINKING_BY_DEFAULT_HINTS`.
THINKING_BY_DEFAULT_HINTS = (
    "gpt-oss", "glm", "nemotron", "qwen3", "deepseek-r1", "deepseek-r2",
    "deepseek-v3.2", "deepseek-v4",
)

VISION_MODEL_HINTS = (
    "gpt-4o", "gpt-4.1", "gpt-5", "claude", "gemini", "llava", "llama3.2-vision",
    "qwen2.5vl", "qwen2-vl", "pixtral", "minicpm-v", "moondream", "vision",
)

COMPATIBLE_PROVIDERS = ("groq", "cerebras", "nvidia", "openrouter", "github")


def model_supports_reasoning(model: str) -> bool:
    return any(hint in (model or "").lower() for hint in REASONING_MODEL_HINTS)


def thinks_by_default(model: str) -> bool:
    return any(hint in (model or "").lower() for hint in THINKING_BY_DEFAULT_HINTS)


def model_supports_vision(provider: str, model: str) -> bool:
    if provider.startswith("gemini"):
        return True  # every current Gemini chat model is multimodal
    if provider == "cerebras":
        return False  # text-only catalogue
    return any(hint in (model or "").lower() for hint in VISION_MODEL_HINTS)


def resolve(provider: str, model: str, defaults: ProviderCapabilities) -> ProviderCapabilities:
    """Bake per-model overrides into a provider instance's declared capabilities.

    The `== "gemini"` / `== "ollama"` comparisons are legacy's exactly. They are
    dead branches in practice — registry keys are `gemini_1` and the local model
    name — but equivalence-first (hard rule #3) means the wart moves with the
    code rather than being quietly corrected here. Gemini's per-model reasoning
    flag is instead resolved at construction, where the instance knows its knob.
    """
    tools, reasoning = defaults.tools, defaults.reasoning
    structured_output = defaults.structured_output
    if provider == "ollama":
        tools, reasoning = True, False  # a prompted fallback always exists
    elif provider in COMPATIBLE_PROVIDERS:
        reasoning = model_supports_reasoning(model)
    # Vision is model-dependent, so resolve it before the direct-adapter block
    # below — that block's explicit True is the final word for openai-*/anthropic-*
    # and must not be clobbered by this hint-based guess.
    vision = model_supports_vision(provider, model)
    if provider.startswith(("openai-", "anthropic-")):
        tools = structured_output = reasoning = vision = True
    return ProviderCapabilities(
        streaming=defaults.streaming, tools=tools, vision=vision,
        structured_output=structured_output, reasoning=reasoning,
        embeddings=defaults.embeddings, max_context_tokens=defaults.max_context_tokens)
