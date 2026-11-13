"""Tests for the replay viewer (report.py).

report.py is a read-only consumer of `state/sessions/<sid>/`, so every test
here builds a session on disk, renders it, and asserts on the HTML. No
gateway, no network, no browser.

The cases that matter are the ones where a run went wrong — a report that
only renders happy-path sessions is useless for the failure demos.
"""

from __future__ import annotations

import re
import sys
import time
from pathlib import Path

import networkx as nx
import pytest

CODE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CODE))

import report  # noqa: E402
from persistence import SessionStore  # noqa: E402
from schemas import AgentResult, BrowserOutput, NodeState  # noqa: E402


# ── fixture plumbing ─────────────────────────────────────────────────────────

@pytest.fixture
def session(tmp_path, monkeypatch):
    """Redirect the session root at tmp_path and hand back a builder."""
    root = tmp_path / "sessions"
    root.mkdir()
    monkeypatch.setattr("persistence.SESSIONS_ROOT", root)
    monkeypatch.setattr("report.SESSIONS_ROOT", root)

    class Builder:
        def __init__(self, sid="s_test"):
            self.sid = sid
            self.root = root
            self.store = SessionStore(sid)
            self.g = nx.DiGraph()
            self.t0 = time.time() - 60

        def query(self, q):
            self.store.write_query(q)
            return self

        def node(self, nid, skill, inputs, status, result, meta=None, started=None):
            self.g.add_node(nid, skill=skill, inputs=inputs, metadata=meta or {},
                            status=status, result=result)
            for i in inputs:
                if i.startswith("n:"):
                    self.g.add_edge(i, nid)
            self.store.write_node(NodeState(
                node_id=nid, skill=skill, status=status, inputs=inputs,
                result=result, prompt_sent="(prompt)",
                started_at=started if started is not None else self.t0,
                completed_at=(started if started is not None else self.t0) + 2))
            return self

        def render(self):
            self.store.write_graph(self.g)
            return report.build_report(self.sid, use_gateway=False)

    return Builder


def _ok(name, output, **kw):
    return AgentResult(success=True, agent_name=name, output=output,
                       provider="gemini", elapsed_s=kw.pop("elapsed", 1.0), **kw)


# ── the happy path ───────────────────────────────────────────────────────────

def test_all_eight_sections_render(session):
    html = (session()
            .query("Compare the top 3 HF text-generation models by likes.")
            .node("n:1", "planner", ["USER_QUERY"], "complete", _ok("planner", {}))
            .node("n:2", "browser", [], "complete", _ok("browser", BrowserOutput(
                url="https://huggingface.co/models", goal="filter and sort",
                path="a11y", turns=3, content="x" * 500,
                final_url="https://huggingface.co/models?sort=likes",
                actions=[{"turn": 1, "actions": [{"type": "click", "mark": 4}],
                          "outcome": "ok"}]).model_dump()))
            .node("n:3", "formatter", ["USER_QUERY", "n:2"], "complete",
                  _ok("formatter", {"final_answer": "| a | b |\n|---|---|\n| 1 | 2 |"}))
            .render())

    for sid_ in ("goal", "dag", "path", "actions", "shots", "extracted", "final", "cost"):
        assert f'<section id="{sid_}">' in html, f"missing section {sid_}"
    assert html.count("<h2>") == 8


def test_report_is_self_contained(session):
    """No external fetches — the page must survive being emailed as one file."""
    html = (session()
            .query("q")
            .node("n:1", "planner", ["USER_QUERY"], "complete", _ok("planner", {}))
            .render())
    external = re.findall(r'(?:src|href)="(https?://[^"]+)"', html)
    assert external == [], f"external references found: {external}"
    assert "<script" not in html


def test_markdown_table_becomes_html_table(session):
    md = ("| model | likes |\n|---|---|\n"
          "| deepseek-ai/DeepSeek-R1 | 12.4k |\n"
          "| Qwen/Qwen2.5-72B | 7.8k |\n\nDeepSeek leads.")
    html = (session()
            .query("compare")
            .node("n:1", "formatter", ["USER_QUERY"], "complete",
                  _ok("formatter", {"final_answer": md}))
            .render())
    final = html.split('<section id="final">')[1].split("</section>")[0]
    assert final.count("<tr>") == 3          # header + 2 data rows
    assert "<th>model</th>" in final
    assert "deepseek-ai/DeepSeek-R1" in final
    assert "<p>DeepSeek leads.</p>" in final  # trailing prose survives


def test_ragged_table_row_is_padded_not_dropped(session):
    """A ragged row is real signal about distiller output; show it."""
    md = "| a | b | c |\n|---|---|---|\n| 1 | 2 |\n"
    html = (session().query("q")
            .node("n:1", "formatter", ["USER_QUERY"], "complete",
                  _ok("formatter", {"final_answer": md}))
            .render())
    final = html.split('<section id="final">')[1].split("</section>")[0]
    assert final.count("<tr>") == 2
    assert final.count("<td>") == 3          # padded to the header width


def test_distiller_rows_render_as_table(session):
    html = (session().query("q")
            .node("n:1", "distiller", [], "complete", _ok("distiller", {
                "columns": ["model", "likes"],
                "rows": [{"model": "A", "likes": "9"}, {"model": "B", "likes": "3"}],
                "rationale": "read from n:0"}))
            .render())
    ext = html.split('<section id="extracted">')[1].split("</section>")[0]
    assert "<th>model</th>" in ext and "<th>likes</th>" in ext
    assert ext.count("<tr>") == 3
    assert "read from n:0" in ext


# ── the failure paths ────────────────────────────────────────────────────────

def test_gateway_blocked_is_surfaced_distinctly(session):
    """The blocked path is a demo deliverable, not just an error — it must be
    labelled as such rather than rendering as a generic failure."""
    blocked = AgentResult(
        success=False, agent_name="browser", error_code="gateway_blocked",
        error="gateway_blocked (captcha) detected after JS render at https://redfin.com/",
        elapsed_s=0.9,
        output=BrowserOutput(url="https://www.redfin.com", goal="find houses",
                             path="extract", turns=0).model_dump())
    html = (session().query("find houses on redfin")
            .node("n:1", "planner", ["USER_QUERY"], "complete", _ok("planner", {}))
            .node("n:2", "browser", [], "failed", blocked)
            .render())
    path = html.split('<section id="path">')[1].split("</section>")[0]
    assert "gateway_blocked" in path
    assert "CAPTCHA" in path                        # the explanatory blurb
    assert "re-invoked the planner" in path
    assert 'class="pill failed"' in path


def test_critic_fail_verdict_is_shown(session):
    html = (session().query("q")
            .node("n:1", "critic", [], "complete", _ok("critic", {
                "verdict": "fail",
                "rationale": "row 2 has no source_url present in the inputs"}))
            .render())
    ext = html.split('<section id="extracted">')[1].split("</section>")[0]
    assert "fail" in ext and "row 2 has no source_url" in ext
    assert 'class="pill failed"' in ext


def test_missing_formatter_does_not_crash(session):
    html = (session().query("q")
            .node("n:1", "planner", ["USER_QUERY"], "failed",
                  AgentResult(success=False, agent_name="planner", error="boom"))
            .render())
    assert "did not reach its terminal node" in html


def test_cost_section_degrades_when_gateway_down(session):
    """Turn counts come from disk and must survive an unreachable gateway."""
    html = (session().query("q")
            .node("n:1", "browser", [], "complete", _ok("browser", BrowserOutput(
                url="u", goal="g", path="a11y", turns=7).model_dump()))
            .render())
    cost = html.split('<section id="cost">')[1].split("</section>")[0]
    assert "skipped (--no-gateway)" in cost
    assert "<b>7</b>" in cost                       # browser turns still reported


def test_no_sessions_raises_cleanly(session, tmp_path):
    with pytest.raises(SystemExit, match="no nodes under"):
        report.build_report("does_not_exist", use_gateway=False)


# ── artifacts ────────────────────────────────────────────────────────────────

def test_screenshots_and_legends_are_inlined(session, tmp_path):
    from PIL import Image
    b = session().query("q")
    started = b.t0 + 5
    b.node("n:1", "browser", [], "complete", _ok("browser", BrowserOutput(
        url="u", goal="g", path="vision", turns=2).model_dump()), started=started)

    art = b.root / b.sid / "browser" / f"browser_{int(started)}" / "vision"
    art.mkdir(parents=True)
    for i in (1, 2):
        Image.new("RGB", (1366, 900), (250, 250, 250)).save(art / f"turn_{i:02d}_marked.png")
        (art / f"turn_{i:02d}_legend.txt").write_text('[1]<button>Go</button>')

    html = b.render()
    shots = html.split('<section id="shots">')[1].split("</section>")[0]
    assert shots.count('src="data:image/png;base64,') == 2
    assert "[1]&lt;button&gt;Go&lt;/button&gt;" in shots     # legend escaped, not executed
    assert "<code>n:1</code>" in shots                       # matched to its node


def test_empty_legend_is_called_out_as_escalation_evidence(session):
    """An empty legend is *why* the cascade escalates to vision. It is the
    single most explanatory artifact in a vision run, so it gets a callout
    rather than rendering as an unremarkable 0-byte file."""
    from PIL import Image
    b = session().query("q")
    started = b.t0 + 5
    b.node("n:1", "browser", [], "complete", _ok("browser", BrowserOutput(
        url="u", goal="g", path="vision", turns=1).model_dump()), started=started)
    art = b.root / b.sid / "browser" / f"browser_{int(started)}" / "a11y"
    art.mkdir(parents=True)
    Image.new("RGB", (100, 100)).save(art / "turn_01_raw.png")
    (art / "turn_01_legend.txt").write_text("")

    shots = b.render().split('<section id="shots">')[1].split("</section>")[0]
    assert "EMPTY" in shots and "escalation to vision" in shots


def test_multiple_layer_dirs_flagged_as_real_escalation(session):
    from PIL import Image
    b = session().query("q")
    started = b.t0 + 5
    b.node("n:1", "browser", [], "complete", _ok("browser", BrowserOutput(
        url="u", goal="g", path="vision", turns=1).model_dump()), started=started)
    base = b.root / b.sid / "browser" / f"browser_{int(started)}"
    for layer in ("a11y", "vision"):
        d = base / layer
        d.mkdir(parents=True)
        Image.new("RGB", (100, 100)).save(d / "turn_01_raw.png")

    shots = b.render().split('<section id="shots">')[1].split("</section>")[0]
    assert "cascade genuinely escalated" in shots


def test_artifacts_attach_to_the_right_node_when_two_browsers_run(session):
    """Two browser nodes, two artifact dirs. Each dir belongs to the node that
    started before it — nearest-match would flip these."""
    from PIL import Image
    b = session().query("q")
    first, second = b.t0 + 5, b.t0 + 40
    for nid, st in (("n:1", first), ("n:2", second)):
        b.node(nid, "browser", [], "complete", _ok("browser", BrowserOutput(
            url="u", goal="g", path="a11y", turns=1).model_dump()), started=st)
    for st in (first, second):
        d = b.root / b.sid / "browser" / f"browser_{int(st)}" / "a11y"
        d.mkdir(parents=True)
        Image.new("RGB", (100, 100)).save(d / "turn_01_raw.png")

    shots = b.render().split('<section id="shots">')[1].split("</section>")[0]
    h3s = re.findall(r"<h3><code>(n:\d)</code> — <span class='muted'>browser_(\d+)",
                     shots)
    assert h3s == [("n:1", str(int(first))), ("n:2", str(int(second)))]


# ── DAG ──────────────────────────────────────────────────────────────────────

def test_dag_svg_has_a_box_per_node_and_edges(session):
    html = (session().query("q")
            .node("n:1", "planner", ["USER_QUERY"], "complete", _ok("planner", {}))
            .node("n:2", "browser", ["n:1"], "complete", _ok("browser", {}))
            .node("n:3", "formatter", ["n:2"], "failed",
                  AgentResult(success=False, agent_name="formatter", error="x"))
            .render())
    dag = html.split('<section id="dag">')[1].split("</section>")[0]
    assert dag.count('<rect') == 3
    assert dag.count("<path d=") == 3        # 2 edges + 1 arrowhead marker path
    assert "#3fb950" in dag                  # complete stroke
    assert "#f85149" in dag                  # failed stroke


def test_interactive_action_count_excludes_done(session):
    html = (session().query("q")
            .node("n:1", "browser", [], "complete", _ok("browser", BrowserOutput(
                url="u", goal="g", path="a11y", turns=2,
                actions=[
                    {"turn": 1, "actions": [{"type": "click", "mark": 1},
                                            {"type": "type", "mark": 2, "value": "x"}],
                     "outcome": "ok | ok"},
                    {"turn": 2, "actions": [{"type": "done", "success": True}],
                     "outcome": "done(True)"}]).model_dump()))
            .render())
    acts = html.split('<section id="actions">')[1].split("</section>")[0]
    assert "<strong>2</strong> interactive actions" in acts


def test_action_error_outcome_is_flagged(session):
    html = (session().query("q")
            .node("n:1", "browser", [], "complete", _ok("browser", BrowserOutput(
                url="u", goal="g", path="a11y", turns=1,
                actions=[{"turn": 1, "actions": [{"type": "click", "mark": 99}],
                          "outcome": "error: no element with mark 99"}]).model_dump()))
            .render())
    acts = html.split('<section id="actions">')[1].split("</section>")[0]
    assert 'class="pill failed"' in acts
