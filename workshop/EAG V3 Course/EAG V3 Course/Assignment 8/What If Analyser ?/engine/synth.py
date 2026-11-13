"""Turn a resolved graph's outcomes into a 3-sentence narrative.

One LLM call per scenario. We pass ONLY the outcome nodes (sign, magnitude,
contested, trace) — not the full graph — because that is all the narrative
needs. All four scenarios run in parallel via ThreadPoolExecutor.

These remain the pipeline's four final calls and run concurrently.
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor

from dotenv import load_dotenv
from google import genai
from google.genai import types

# Match extraction's local-development credential loading behavior.
load_dotenv()

from engine.schema import Graph

MODEL = "gemini-3.1-pro-preview"

# The prompt deliberately constrains both format and analytical content so the
# four scenario notes can be scanned side by side.
_SYSTEM = """You are an analyst writing a terse scenario note. You are given \
the resolved outcomes of a causal model under one scenario. Write EXACTLY three \
sentences, plain prose, no headers, no bullets, no preamble:
1. What happens to the outcomes (direction and rough size).
2. The single mechanism that drove the biggest move.
3. What observation would falsify this scenario.
Be concrete and specific. Do not hedge with "it depends"."""

# Convert propagation's machine representation into prose before asking the LLM
# to synthesize; the model never has to infer what a sign bucket means.
_ARROW = {
    (1, "high"): "sharply up",
    (1, "med"): "up",
    (1, "low"): "slightly up",
    (-1, "high"): "sharply down",
    (-1, "med"): "down",
    (-1, "low"): "slightly down",
}


def _describe_outcome(node) -> str:
    """Serialize one resolved outcome and its audit trace for the prompt."""
    # Contested is checked first because a zero net sign may hide opposing pushes.
    if node.contested:
        direction = "contested (offsetting forces)"
    elif node.sign == 0:
        direction = "roughly flat"
    else:
        direction = _ARROW.get((node.sign, node.magnitude), "moves")
    # Keep the deterministic trace verbatim so the narrative is grounded in the
    # same mechanisms displayed in the UI.
    trace = "; ".join(node.trace) if node.trace else "(no upstream drivers)"
    return f"- {node.label}: {direction}\n    drivers: {trace}"


def _build_prompt(resolved: Graph, scenario_name: str) -> str:
    """Build the minimal prompt needed to narrate a resolved scenario."""
    # Intermediate nodes have already done their job during propagation; sending
    # outcomes only reduces tokens and prevents the narrative from drifting.
    outcomes = [n for n in resolved.nodes if n.node_type == "outcome"]
    lines = "\n".join(_describe_outcome(n) for n in outcomes)
    return (
        f"Scenario: {scenario_name}\n\n"
        f"Resolved outcomes:\n{lines}\n\n"
        "Write the three-sentence note."
    )


def synthesize(
    resolved: Graph,
    scenario_name: str,
    client: genai.Client | None = None,
) -> str:
    """Return a 3-sentence narrative for one resolved scenario."""
    if client is None:
        # Callers may inject a fake or shared client for tests and batch work.
        if not (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")):
            raise RuntimeError("GEMINI_API_KEY is not set.")
        client = genai.Client()

    # Unlike extraction, synthesis expects plain text rather than JSON.
    resp = client.models.generate_content(
        model=MODEL,
        contents=_build_prompt(resolved, scenario_name),
        config=types.GenerateContentConfig(
            system_instruction=_SYSTEM,
            # Thinking tokens and visible text share this limit. Leave enough
            # room for Pro's low-level reasoning plus the requested 3 sentences.
            max_output_tokens=4096,
            # Pro does not support a no-thinking setting. Low keeps this simple
            # writing task fast while retaining the model's required reasoning.
            thinking_config=types.ThinkingConfig(thinking_level="LOW"),
        ),
    )
    # The SDK may expose no text for a blocked/empty response; normalize to "".
    return (resp.text or "").strip()


def synthesize_all(
    scenarios: list[tuple[str, Graph]],
    client: genai.Client | None = None,
) -> list[str]:
    """Synthesize narratives for many (name, resolved_graph) pairs in parallel.

    Returns narratives in the same order as the input list.
    """
    if client is None:
        if not (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")):
            raise RuntimeError("GEMINI_API_KEY is not set.")
        client = genai.Client()

    # One worker per scenario minimizes latency for the expected four-item batch;
    # `or 1` also makes the empty-input case valid.
    with ThreadPoolExecutor(max_workers=len(scenarios) or 1) as pool:
        futures = [
            pool.submit(synthesize, resolved, name, client)
            for (name, resolved) in scenarios
        ]
        # Reading futures in submission order preserves alignment with UI names.
        return [f.result() for f in futures]
