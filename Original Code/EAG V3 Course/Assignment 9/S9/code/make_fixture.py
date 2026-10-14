"""Build a synthetic session so the replay viewer can be demonstrated without
a provider key.

This writes `state/sessions/s9_fixture/` in the exact shapes flow.py persists
— NodeState JSON, graph.json, per-turn browser artifacts — with generated
placeholder screenshots.

IMPORTANT: this is NOT a real agent run. No browser was driven and no page was
visited; the values are hand-written. Use it to exercise report.py, never as
evidence of agent behaviour.

    uv run python make_fixture.py
    uv run python report.py s9_fixture --no-gateway --open
"""
import sys, time
from pathlib import Path

CODE = Path(__file__).resolve().parent
sys.path.insert(0, str(CODE))

import networkx as nx
from PIL import Image, ImageDraw
from persistence import SessionStore, SESSIONS_ROOT
from schemas import AgentResult, BrowserOutput, NodeState

SID = "s9_fixture"
QUERY = ("Compare the top 3 Hugging Face text-generation models sorted by likes. "
         "For each give the model name, parameter count, likes, and a one-line description.")

t0 = time.time() - 60
store = SessionStore(SID)
store.write_query(QUERY)

g = nx.DiGraph()

def node(nid, skill, inputs, status, result, meta=None, started=None, prompt="(prompt)"):
    g.add_node(nid, skill=skill, inputs=inputs, metadata=meta or {}, status=status,
               result=result)
    for i in inputs:
        if i.startswith("n:"):
            g.add_edge(i, nid)
    store.write_node(NodeState(node_id=nid, skill=skill, status=status, inputs=inputs,
                              result=result, prompt_sent=prompt,
                              started_at=started or t0, completed_at=(started or t0) + 2))

# n:1 planner
node("n:1", "planner", ["USER_QUERY"], "complete",
     AgentResult(success=True, agent_name="planner", provider="gemini", elapsed_s=4.8,
                 output={"rationale": "Drive HF's own filter+sort widgets, then tabulate."}),
     meta={"label": "plan"}, started=t0)

# n:2 browser — a11y path, escalated from extract
browser_start = t0 + 5
actions = [
    {"turn": 1, "actions": [{"type": "click", "mark": 14, "note": "open Tasks filter"}],
     "outcome": "ok"},
    {"turn": 2, "actions": [{"type": "type", "mark": 21, "value": "Text Generation"},
                            {"type": "key", "value": "Enter"}], "outcome": "ok | ok"},
    {"turn": 3, "actions": [{"type": "click", "mark": 9, "note": "Sort: Trending dropdown"}],
     "outcome": "ok"},
    {"turn": 4, "actions": [{"type": "click", "mark": 33, "note": "Most likes"}], "outcome": "ok"},
    {"turn": 5, "actions": [{"type": "scroll", "direction": "down", "amount": 600}],
     "outcome": "ok"},
    {"turn": 6, "actions": [{"type": "done", "success": True,
                             "note": "top 3 model cards read"}], "outcome": "done(True)"},
]
bo = BrowserOutput(
    url="https://huggingface.co/models", goal=(
        "Set the Tasks filter to Text Generation, then set Sort to Most Likes. "
        "Read the top 3 model cards and report model id, likes, parameter count, "
        "and the link to each model page."),
    path="a11y", turns=6, actions=actions,
    final_url="https://huggingface.co/models?pipeline_tag=text-generation&sort=likes",
    content=("deepseek-ai/DeepSeek-R1 685B params 12.4k likes reasoning model\n"
             "meta-llama/Llama-3.3-70B-Instruct 70B params 9.1k likes instruction tuned\n"
             "Qwen/Qwen2.5-72B-Instruct 72B params 7.8k likes multilingual\n") * 12)
node("n:2", "browser", [], "complete",
     AgentResult(success=True, agent_name="browser", provider="gemini", elapsed_s=17.4,
                 output=bo.model_dump()), meta={"label": "hf"}, started=browser_start)

# n:3 distiller with the new rows shape
rows = [
    {"model": "deepseek-ai/DeepSeek-R1", "parameter count": "685B", "likes": "12.4k",
     "description": "Reasoning-focused open model trained with RL.",
     "source_url": "https://huggingface.co/deepseek-ai/DeepSeek-R1"},
    {"model": "meta-llama/Llama-3.3-70B-Instruct", "parameter count": "70B", "likes": "9.1k",
     "description": "Instruction-tuned general-purpose chat model.",
     "source_url": "https://huggingface.co/meta-llama/Llama-3.3-70B-Instruct"},
    {"model": "Qwen/Qwen2.5-72B-Instruct", "parameter count": "72B", "likes": "7.8k",
     "description": "Multilingual instruction model, strong on code.",
     "source_url": "https://huggingface.co/Qwen/Qwen2.5-72B-Instruct"},
]
node("n:3", "distiller", ["n:2"], "complete",
     AgentResult(success=True, agent_name="distiller", provider="gemini", elapsed_s=3.9,
                 output={"columns": ["model", "parameter count", "likes", "description",
                                     "source_url"],
                         "rows": rows,
                         "comparison": {"winner": "deepseek-ai/DeepSeek-R1",
                                        "reason": "highest like count"},
                         "rationale": "Each row is read from the n:2 model cards."}),
     meta={"label": "tbl"}, started=t0 + 24)

# n:5 critic (orchestrator auto-inserted between distiller and formatter)
node("n:5", "critic", ["USER_QUERY", "n:3"], "complete",
     AgentResult(success=True, agent_name="critic", provider="gemini", elapsed_s=1.2,
                 output={"verdict": "pass",
                         "rationale": "All three rows carry every column and each "
                                      "source_url appears in the browser output."}),
     meta={"target": "n:3", "child": "n:4"}, started=t0 + 29)

# n:4 formatter
table = ("| model | parameter count | likes | description | source_url |\n"
         "|---|---|---|---|---|\n"
         + "".join(f"| {r['model']} | {r['parameter count']} | {r['likes']} | "
                   f"{r['description']} | {r['source_url']} |\n" for r in rows))
node("n:4", "formatter", ["USER_QUERY", "n:3"], "complete",
     AgentResult(success=True, agent_name="formatter", provider="gemini", elapsed_s=3.7,
                 output={"final_answer": table + (
                     "\nDeepSeek-R1 leads on likes (12.4k) by a wide margin, and is also "
                     "by far the largest at 685B parameters. Llama-3.3-70B and Qwen2.5-72B "
                     "are close in both size and popularity.\n")}),
     meta={"label": "out"}, started=t0 + 31)
g.add_edge("n:5", "n:4")
g.remove_edge("n:3", "n:4") if g.has_edge("n:3", "n:4") else None

store.write_graph(g)

# Browser artifacts: an a11y attempt directory with per-turn screenshots + legends.
art = SESSIONS_ROOT / SID / "browser" / f"browser_{int(browser_start)}" / "a11y"
art.mkdir(parents=True, exist_ok=True)
for i in range(1, 7):
    im = Image.new("RGB", (1366, 900), (250, 250, 252))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, 1366, 70], fill=(255, 255, 255))
    d.text((40, 30), f"huggingface.co/models  —  turn {i}", fill=(20, 20, 20))
    for c in range(3):
        d.rectangle([40 + c * 430, 120, 400 + c * 430, 380], outline=(200, 200, 210), width=2)
        d.text((60 + c * 430, 150), f"model card {c + 1}", fill=(40, 40, 40))
    im.save(art / f"turn_{i:02d}_raw.png")
    (art / f"turn_{i:02d}_legend.txt").write_text(
        "\n".join(f'[{n}]<button role="button">Filter option {n}</button>'
                  for n in range(1, 26)), encoding="utf-8")

print(f"fixture written: {SESSIONS_ROOT / SID}")
