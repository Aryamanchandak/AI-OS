"""Session 9 replay viewer — renders a persisted run as one self-contained HTML page.

This is a READ-ONLY consumer of `state/sessions/<sid>/`. It imports nothing
from flow.py and mutates nothing: the assignment's "the orchestrator must not
be modified" constraint is satisfied structurally, because this script only
ever reads files the orchestrator already wrote.

Everything the report shows is already on disk when a run finishes:

  1. Original user goal          query.txt
  2. Planner DAG                 graph.json (nodes + edges + status)
  3. Browser path chosen         BrowserOutput.path / AgentResult.error_code
  4. Browser actions taken       BrowserOutput.actions  (per-turn action lists)
  5. Screenshots / page-state    browser/<ts>/<layer>/turn_NN_{raw,marked}.png
                                 browser/<ts>/<layer>/turn_NN_legend.txt
  6. Extracted data              BrowserOutput.content, distiller rows/fields
  7. Final comparison table      formatter final_answer (Markdown → HTML)
  8. Turn count and cost         per-node turns/elapsed + gateway cost ledger

The one thing NOT on disk is the cost rollup — that lives in the gateway's
SQLite ledger and is fetched over HTTP at report time. When the gateway is
down the report still renders; the cost section degrades to a note plus the
locally-known turn counts and wall-clock timings.

Usage:
    uv run python report.py <session_id> [-o path.html] [--no-gateway] [--open]
    uv run python report.py --list
"""

from __future__ import annotations

import argparse
import base64
import html
import io
import json
import re
import sys
import webbrowser
from dataclasses import dataclass, field
from pathlib import Path

from persistence import SESSIONS_ROOT, SessionStore, list_sessions
from schemas import NodeState

GATEWAY_URL = "http://localhost:8109"

# Screenshots are downscaled before base64-inlining. A 12-turn two-layer run
# would otherwise produce a 40 MB page. 760px keeps the marked element
# numbers legible while cutting each PNG to roughly a tenth.
SCREENSHOT_MAX_WIDTH = 760


# ── data collection ──────────────────────────────────────────────────────────

@dataclass
class Turn:
    """One driver turn's artifacts, as found on disk."""
    index: int
    raw_png: Path | None = None
    marked_png: Path | None = None
    legend: Path | None = None


@dataclass
class BrowserRun:
    """One BrowserSkill.run() invocation's artifact directory.

    A single session can hold several: one per browser node, plus one
    subdirectory per cascade layer the skill actually attempted. The `a11y`
    subdir existing alongside `vision` is itself evidence of escalation.
    """
    dir_name: str
    started_at: float          # parsed from the `browser_<unix_ts>` dir name
    layers: dict[str, list[Turn]] = field(default_factory=dict)
    node_id: str | None = None  # filled in by _attach_artifacts_to_nodes


def _parse_turn_files(layer_dir: Path) -> list[Turn]:
    turns: dict[int, Turn] = {}
    for p in sorted(layer_dir.glob("turn_*")):
        m = re.match(r"turn_(\d+)_(raw|marked|legend)", p.name)
        if not m:
            continue
        idx = int(m.group(1))
        t = turns.setdefault(idx, Turn(index=idx))
        kind = m.group(2)
        if kind == "raw":
            t.raw_png = p
        elif kind == "marked":
            t.marked_png = p
        else:
            t.legend = p
    return [turns[k] for k in sorted(turns)]


def collect_browser_runs(session_id: str) -> list[BrowserRun]:
    """Walk `state/sessions/<sid>/browser/browser_<ts>/<layer>/turn_*`."""
    root = SESSIONS_ROOT / session_id / "browser"
    if not root.exists():
        return []
    runs: list[BrowserRun] = []
    for d in sorted(root.iterdir()):
        if not d.is_dir():
            continue
        m = re.match(r"browser_(\d+)", d.name)
        started = float(m.group(1)) if m else 0.0
        run = BrowserRun(dir_name=d.name, started_at=started)
        for layer_dir in sorted(d.iterdir()):
            if not layer_dir.is_dir():
                continue
            turns = _parse_turn_files(layer_dir)
            if turns:
                run.layers[layer_dir.name] = turns
        if run.layers:
            runs.append(run)
    return runs


def _attach_artifacts_to_nodes(runs: list[BrowserRun],
                               states: list[NodeState]) -> None:
    """Match each artifact directory to the browser node that produced it.

    BrowserSkill names its directory `browser_<int(time.time())>` at the top
    of run(), a beat after the orchestrator stamps the node's `started_at`.
    So the correct owner is the browser node with the largest `started_at`
    that is not after the directory's timestamp (allowing a second of skew).
    Greedy nearest-match would mis-assign when two browser nodes run
    concurrently; anchoring on "started before this directory existed" does
    not.
    """
    browser_states = sorted(
        (s for s in states if s.skill == "browser" and s.started_at),
        key=lambda s: s.started_at or 0.0,
    )
    for run in runs:
        best: NodeState | None = None
        for s in browser_states:
            if (s.started_at or 0.0) <= run.started_at + 1.0:
                best = s
            else:
                break
        if best is not None:
            run.node_id = best.node_id


def fetch_cost(session_id: str, *, enabled: bool = True) -> tuple[dict | None, str | None]:
    """Returns (rollup, error_note). Never raises — a down gateway is a
    degraded report, not a failed one."""
    if not enabled:
        return None, "skipped (--no-gateway)"
    try:
        import httpx
        r = httpx.get(f"{GATEWAY_URL}/v1/cost/by_agent",
                      params={"session": session_id}, timeout=5.0)
        r.raise_for_status()
        return r.json(), None
    except Exception as e:  # noqa: BLE001 - any failure degrades identically
        return None, f"gateway unreachable at {GATEWAY_URL} ({type(e).__name__})"


# ── rendering helpers ────────────────────────────────────────────────────────

def _b64_png(path: Path, max_width: int = SCREENSHOT_MAX_WIDTH) -> str | None:
    """Downscale and base64-encode a PNG for inline embedding. Falls back to
    the raw bytes when Pillow is unavailable."""
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    try:
        from PIL import Image
        im = Image.open(io.BytesIO(raw))
        if im.width > max_width:
            h = int(im.height * (max_width / im.width))
            im = im.resize((max_width, h), Image.LANCZOS)
            buf = io.BytesIO()
            im.convert("RGB").save(buf, format="PNG", optimize=True)
            raw = buf.getvalue()
    except Exception:  # noqa: BLE001 - Pillow missing or image unreadable
        pass
    return "data:image/png;base64," + base64.b64encode(raw).decode("ascii")


def _md_inline(text: str) -> str:
    """Escape, then apply the small subset of inline Markdown the formatter
    actually emits."""
    t = html.escape(text)
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
    t = re.sub(r"\[([^\]]+)\]\((https?://[^\s)]+)\)",
               r'<a href="\2" target="_blank" rel="noopener">\1</a>', t)
    t = re.sub(r"(?<!\")(?<!>)(https?://[^\s<)\]]+)",
               r'<a href="\1" target="_blank" rel="noopener">\1</a>', t)
    return t


def md_to_html(md: str) -> str:
    """Minimal Markdown → HTML, sized to what the Formatter emits: tables,
    headings, bullets, paragraphs. A full parser would be dead weight here."""
    lines = (md or "").replace("\\n", "\n").split("\n")
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Table: a header row followed by a |---|---| separator.
        if (stripped.startswith("|") and i + 1 < len(lines)
                and re.match(r"^\s*\|[\s:|-]+\|\s*$", lines[i + 1])):
            header = [c.strip() for c in stripped.strip("|").split("|")]
            i += 2
            rows: list[list[str]] = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            out.append('<div class="table-scroll"><table class="cmp">')
            out.append("<thead><tr>"
                       + "".join(f"<th>{_md_inline(c)}</th>" for c in header)
                       + "</tr></thead><tbody>")
            for r in rows:
                # Pad ragged rows rather than dropping cells — a ragged row is
                # a real signal about the distiller's output and the report
                # should show it, not hide it.
                r = r + [""] * (len(header) - len(r))
                out.append("<tr>" + "".join(f"<td>{_md_inline(c)}</td>" for c in r) + "</tr>")
            out.append("</tbody></table></div>")
            continue

        if stripped.startswith("#"):
            level = len(stripped) - len(stripped.lstrip("#"))
            out.append(f"<h{min(level + 2, 6)}>{_md_inline(stripped.lstrip('# '))}"
                       f"</h{min(level + 2, 6)}>")
            i += 1
            continue

        if re.match(r"^\s*[-*+]\s+", line) or re.match(r"^\s*\d+[.)]\s+", line):
            items = []
            ordered = bool(re.match(r"^\s*\d+[.)]\s+", line))
            while i < len(lines) and (re.match(r"^\s*[-*+]\s+", lines[i])
                                      or re.match(r"^\s*\d+[.)]\s+", lines[i])):
                items.append(re.sub(r"^\s*(?:[-*+]|\d+[.)])\s+", "", lines[i]))
                i += 1
            tag = "ol" if ordered else "ul"
            out.append(f"<{tag}>" + "".join(f"<li>{_md_inline(x)}</li>" for x in items)
                       + f"</{tag}>")
            continue

        if not stripped:
            i += 1
            continue

        para = []
        while i < len(lines) and lines[i].strip() and not lines[i].strip().startswith(("|", "#", "-", "*")):
            para.append(lines[i].strip())
            i += 1
        if para:
            out.append(f"<p>{_md_inline(' '.join(para))}</p>")
        else:
            out.append(f"<p>{_md_inline(stripped)}</p>")
            i += 1
    return "\n".join(out)


# ── DAG → inline SVG ─────────────────────────────────────────────────────────

_STATUS_FILL = {
    "complete": ("#132e1c", "#3fb950"),
    "failed":   ("#3a1618", "#f85149"),
    "skipped":  ("#2a2520", "#d29922"),
    "running":  ("#152238", "#58a6ff"),
    "pending":  ("#20242b", "#6e7681"),
}


def dag_svg(graph) -> str:
    """Layered left-to-right DAG as inline SVG. No JS, no external library —
    the report has to survive being emailed as a single file."""
    if graph is None or graph.number_of_nodes() == 0:
        return "<p class='muted'>No graph.json found for this session.</p>"

    import networkx as nx

    try:
        layers = list(nx.topological_generations(graph))
    except nx.NetworkXUnfeasible:  # a cycle should be impossible, but don't crash
        layers = [list(graph.nodes)]

    box_w, box_h = 190, 58
    gap_x, gap_y = 90, 26
    pad = 24

    pos: dict[str, tuple[int, int]] = {}
    for col, layer in enumerate(layers):
        for row, nid in enumerate(sorted(layer)):
            pos[nid] = (pad + col * (box_w + gap_x), pad + row * (box_h + gap_y))

    width = pad * 2 + len(layers) * box_w + max(len(layers) - 1, 0) * gap_x
    height = pad * 2 + max((len(l) for l in layers), default=1) * (box_h + gap_y)

    parts = [
        f'<svg viewBox="0 0 {width} {height}" width="100%" '
        f'style="max-width:{width}px" xmlns="http://www.w3.org/2000/svg" '
        f'role="img" aria-label="Planner DAG">',
        '<defs><marker id="arw" viewBox="0 0 10 10" refX="9" refY="5" '
        'markerWidth="6" markerHeight="6" orient="auto-start-reverse">'
        '<path d="M 0 0 L 10 5 L 0 10 z" fill="#6e7681"/></marker></defs>',
    ]

    for u, v in graph.edges():
        if u not in pos or v not in pos:
            continue
        x1, y1 = pos[u][0] + box_w, pos[u][1] + box_h // 2
        x2, y2 = pos[v][0], pos[v][1] + box_h // 2
        mid = (x1 + x2) // 2
        parts.append(
            f'<path d="M {x1} {y1} C {mid} {y1} {mid} {y2} {x2} {y2}" '
            f'fill="none" stroke="#6e7681" stroke-width="1.5" marker-end="url(#arw)"/>'
        )

    for nid, (x, y) in pos.items():
        d = graph.nodes[nid]
        status = d.get("status", "pending")
        fill, stroke = _STATUS_FILL.get(status, _STATUS_FILL["pending"])
        skill = html.escape(str(d.get("skill", "?")))
        label = (d.get("metadata") or {}).get("label") if isinstance(d.get("metadata"), dict) else None
        sub = html.escape(f"{nid}" + (f" · {label}" if label else ""))
        parts.append(
            f'<g><rect x="{x}" y="{y}" width="{box_w}" height="{box_h}" rx="8" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="1.5"/>'
            f'<text x="{x + 12}" y="{y + 24}" fill="#e6edf3" font-size="14" '
            f'font-family="ui-monospace,monospace" font-weight="600">{skill}</text>'
            f'<text x="{x + 12}" y="{y + 43}" fill="#8b949e" font-size="11" '
            f'font-family="ui-monospace,monospace">{sub}</text></g>'
        )

    parts.append("</svg>")
    return "".join(parts)


# ── section builders ─────────────────────────────────────────────────────────

def _pill(text: str, kind: str = "") -> str:
    return f'<span class="pill {kind}">{html.escape(text)}</span>'


_PATH_BLURB = {
    "extract":       "Layer 1 — static HTML via trafilatura. No LLM calls, no browser launched.",
    "deterministic": "Layer 2a — caller-supplied CSS selectors driven through Playwright.",
    "a11y":          "Layer 2b — accessibility/element legend sent as text; no screenshot.",
    "vision":        "Layer 3 — set-of-marks screenshot sent to a vision model.",
}


def section_goal(query: str, session_id: str, states: list[NodeState]) -> str:
    done = sum(1 for s in states if s.status == "complete")
    failed = sum(1 for s in states if s.status == "failed")
    return f"""
<section id="goal">
  <h2>1 · Original user goal</h2>
  <blockquote class="goal">{html.escape(query or '(no query.txt found)')}</blockquote>
  <p class="muted">session <code>{html.escape(session_id)}</code> ·
     {len(states)} nodes · {done} complete · {failed} failed</p>
</section>"""


def section_dag(graph, states: list[NodeState]) -> str:
    rows = []
    for s in states:
        rows.append(
            f"<tr><td><code>{html.escape(s.node_id)}</code></td>"
            f"<td>{html.escape(s.skill)}</td>"
            f"<td>{_pill(s.status, s.status)}</td>"
            f"<td><code>{html.escape(', '.join(s.inputs) or '—')}</code></td>"
            f"<td>{(f'{s.result.elapsed_s:.1f}s' if s.result and s.result.elapsed_s else '—')}</td>"
            f"<td>{html.escape(s.result.provider if s.result and s.result.provider else '—')}</td></tr>"
        )
    return f"""
<section id="dag">
  <h2>2 · Planner DAG</h2>
  <p class="muted">Left to right in topological order. The graph grows at
     runtime — critic nodes are spliced in by the orchestrator, not by the
     planner, and recovery planners appear only if something failed.</p>
  <div class="svg-wrap">{dag_svg(graph)}</div>
  <div class="table-scroll"><table>
    <thead><tr><th>node</th><th>skill</th><th>status</th><th>inputs</th>
      <th>elapsed</th><th>provider</th></tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table></div>
</section>"""


def _browser_nodes(states: list[NodeState]) -> list[NodeState]:
    return [s for s in states if s.skill == "browser"]


def section_path(states: list[NodeState]) -> str:
    bn = _browser_nodes(states)
    if not bn:
        return """
<section id="path"><h2>3 · Browser path chosen</h2>
<p class="muted">No browser nodes in this run.</p></section>"""
    cards = []
    for s in bn:
        out = (s.result.output if s.result else {}) or {}
        code = s.result.error_code if s.result else None
        path = out.get("path") or "—"
        if code == "gateway_blocked":
            headline = _pill("gateway_blocked", "failed")
            blurb = ("The target refused automation (CAPTCHA / Cloudflare / login "
                     "wall). The cascade stopped rather than burning LLM calls, and "
                     "the orchestrator re-invoked the planner to route around it.")
        else:
            headline = _pill(path, "complete" if s.status == "complete" else "failed")
            blurb = _PATH_BLURB.get(path, "")
        cards.append(f"""
    <div class="card">
      <div class="card-head"><code>{html.escape(s.node_id)}</code> {headline}
        <span class="muted">{out.get('turns', 0)} turns ·
        {(f'{s.result.elapsed_s:.1f}s' if s.result else '—')}</span></div>
      <p class="url"><strong>url</strong> {_md_inline(str(out.get('url') or '—'))}</p>
      <p class="url"><strong>final</strong> {_md_inline(str(out.get('final_url') or '—'))}</p>
      <p><strong>goal</strong> {html.escape(str(out.get('goal') or '—'))}</p>
      <p class="muted">{html.escape(blurb)}</p>
      {f'<p class="err">{html.escape(s.result.error or "")}</p>' if s.result and s.result.error else ''}
    </div>""")
    return f"""
<section id="path">
  <h2>3 · Browser path chosen</h2>
  <p class="muted">The cascade tries the cheapest layer first and escalates
     only when a layer returns nothing useful:
     <code>extract → deterministic → a11y → vision</code>. The layer named
     below is the one that actually produced the answer.</p>
  {''.join(cards)}
</section>"""


def section_actions(states: list[NodeState]) -> str:
    bn = _browser_nodes(states)
    blocks = []
    total_actions = 0
    for s in bn:
        out = (s.result.output if s.result else {}) or {}
        actions = out.get("actions") or []
        if not actions:
            blocks.append(f"<p class='muted'><code>{html.escape(s.node_id)}</code>: "
                          f"no interactive turns (path "
                          f"<code>{html.escape(str(out.get('path') or '—'))}</code>).</p>")
            continue
        rows = []
        for turn in actions:
            acts = turn.get("actions") or []
            total_actions += sum(1 for a in acts if a.get("type") != "done")
            pretty = []
            for a in acts:
                t = a.get("type", "?")
                bits = [f"<code>{html.escape(t)}</code>"]
                if a.get("mark") is not None:
                    bits.append(f"mark={a['mark']}")
                if a.get("value"):
                    bits.append(f"value={html.escape(str(a['value'])[:60])!r}")
                if a.get("direction"):
                    bits.append(f"dir={html.escape(str(a['direction']))}")
                if a.get("note"):
                    bits.append(html.escape(str(a["note"])[:120]))
                pretty.append(" ".join(bits))
            outcome = str(turn.get("outcome", ""))
            kind = "failed" if "error" in outcome else "complete"
            rows.append(
                f"<tr><td>{turn.get('turn', '?')}</td>"
                f"<td>{'<br>'.join(pretty) or '—'}</td>"
                f"<td>{_pill(outcome[:60] or 'ok', kind)}</td></tr>"
            )
        blocks.append(f"""
    <h3><code>{html.escape(s.node_id)}</code> — {len(actions)} turns</h3>
    <div class="table-scroll"><table>
      <thead><tr><th>turn</th><th>actions</th><th>outcome</th></tr></thead>
      <tbody>{''.join(rows)}</tbody></table></div>""")
    note = (f"<p class='muted'><strong>{total_actions}</strong> interactive actions "
            f"dispatched across the run (excluding <code>done</code>).</p>")
    return f"""
<section id="actions">
  <h2>4 · Browser actions taken</h2>
  {note}
  {''.join(blocks) or "<p class='muted'>No browser nodes in this run.</p>"}
</section>"""


def section_screenshots(runs: list[BrowserRun]) -> str:
    if not runs:
        return """
<section id="shots"><h2>5 · Screenshots &amp; page-state logs</h2>
<p class="muted">No browser artifacts on disk. An <code>extract</code>-path run
never launches a browser, so this is expected when every browser node resolved
at Layer 1.</p></section>"""
    blocks = []
    for run in runs:
        owner = f"<code>{html.escape(run.node_id)}</code>" if run.node_id else "<em>unmatched</em>"
        layer_names = ", ".join(f"<code>{html.escape(k)}</code>" for k in run.layers)
        blocks.append(f"<h3>{owner} — <span class='muted'>{run.dir_name} · "
                      f"layers attempted: {layer_names}</span></h3>")
        if len(run.layers) > 1:
            blocks.append("<p class='muted'>More than one layer directory means the "
                          "cascade genuinely escalated — the earlier layer ran and "
                          "did not settle the goal.</p>")
        for layer, turns in run.layers.items():
            blocks.append(f"<h4>layer <code>{html.escape(layer)}</code> — "
                          f"{len(turns)} turns</h4><div class='shots'>")
            for t in turns:
                img = t.marked_png or t.raw_png
                cap = "marked (set-of-marks)" if t.marked_png else "raw"
                data = _b64_png(img) if img else None
                legend_html = ""
                if t.legend and t.legend.exists():
                    text = t.legend.read_text(encoding="utf-8", errors="replace")
                    size = len(text.strip())
                    summary = (f"element legend — {size} chars"
                               + (" (EMPTY — no DOM grip, this is what forces "
                                  "escalation to vision)" if size == 0 else ""))
                    legend_html = (f"<details><summary>{html.escape(summary)}</summary>"
                                   f"<pre>{html.escape(text[:8000])}</pre></details>")
                blocks.append(
                    f"<figure>"
                    + (f'<img src="{data}" alt="turn {t.index} {cap}" loading="lazy">'
                       if data else "<div class='muted'>(image unreadable)</div>")
                    + f"<figcaption>turn {t.index:02d} · {cap}</figcaption>"
                    + legend_html + "</figure>"
                )
            blocks.append("</div>")
    return f"""
<section id="shots">
  <h2>5 · Screenshots &amp; page-state logs</h2>
  <p class="muted">One entry per driver turn. The <em>marked</em> screenshots are
     what the vision layer actually saw: numbered dashed boxes over every
     interactive element. The legend is what the a11y layer saw instead.</p>
  {''.join(blocks)}
</section>"""


def section_extracted(states: list[NodeState]) -> str:
    blocks = []
    for s in states:
        if not s.result or not s.result.output:
            continue
        out = s.result.output
        if s.skill == "browser":
            content = out.get("content") or ""
            if content:
                blocks.append(
                    f"<h3><code>{html.escape(s.node_id)}</code> browser — "
                    f"{len(content)} chars extracted</h3>"
                    f"<details><summary>show extracted page text</summary>"
                    f"<pre>{html.escape(content[:12000])}"
                    f"{'…' if len(content) > 12000 else ''}</pre></details>")
        elif s.skill == "distiller":
            blocks.append(f"<h3><code>{html.escape(s.node_id)}</code> distiller</h3>")
            if out.get("rows"):
                cols = out.get("columns") or list(
                    {k for r in out["rows"] if isinstance(r, dict) for k in r})
                head = "".join(f"<th>{html.escape(str(c))}</th>" for c in cols)
                body = ""
                for r in out["rows"]:
                    if not isinstance(r, dict):
                        continue
                    body += "<tr>" + "".join(
                        f"<td>{_md_inline(str(r.get(c, '')))}</td>" for c in cols
                    ) + "</tr>"
                blocks.append(f"<div class='table-scroll'><table class='cmp'>"
                              f"<thead><tr>{head}</tr></thead><tbody>{body}</tbody>"
                              f"</table></div>")
            if out.get("rationale"):
                blocks.append(f"<p class='muted'>{html.escape(str(out['rationale']))}</p>")
            if out.get("fields"):
                blocks.append(f"<pre>{html.escape(json.dumps(out['fields'], indent=2))}</pre>")
        elif s.skill == "critic":
            verdict = str(out.get("verdict", "?"))
            blocks.append(
                f"<h3><code>{html.escape(s.node_id)}</code> critic "
                f"{_pill(verdict, 'complete' if verdict == 'pass' else 'failed')}</h3>"
                f"<p class='muted'>{html.escape(str(out.get('rationale', '')))}</p>")
    return f"""
<section id="extracted">
  <h2>6 · Extracted data</h2>
  <p class="muted">Raw page text from the browser, the structured rows the
     distiller pulled out of it, and the critic's verdict on those rows.</p>
  {''.join(blocks) or "<p class='muted'>Nothing extracted.</p>"}
</section>"""


def section_final(states: list[NodeState]) -> str:
    answer = None
    for s in reversed(states):
        if s.skill == "formatter" and s.result and s.result.output.get("final_answer"):
            answer = s.result.output["final_answer"]
            break
    if not answer:
        return """
<section id="final"><h2>7 · Final comparison table</h2>
<p class="muted">No formatter output — the run did not reach its terminal node.</p>
</section>"""
    return f"""
<section id="final">
  <h2>7 · Final comparison table</h2>
  <div class="answer">{md_to_html(answer)}</div>
</section>"""


def section_cost(states: list[NodeState], cost: dict | None,
                 cost_err: str | None) -> str:
    turns = sum(((s.result.output.get("turns") or 0) if s.result else 0)
                for s in states if s.skill == "browser")
    wall = sum((s.result.elapsed_s or 0.0) for s in states if s.result)
    local = f"""
  <div class="stats">
    <div class="stat"><b>{len(states)}</b><span>nodes executed</span></div>
    <div class="stat"><b>{turns}</b><span>browser turns</span></div>
    <div class="stat"><b>{wall:.1f}s</b><span>summed node time</span></div>
  </div>"""
    if cost is None:
        return f"""
<section id="cost">
  <h2>8 · Turn count &amp; cost summary</h2>
  {local}
  <p class="muted">Gateway cost ledger unavailable — {html.escape(cost_err or 'unknown')}.
     Turn counts and timings above come from the persisted session and are
     unaffected.</p>
</section>"""
    rows, tot_calls, tot_in, tot_out, tot_usd = [], 0, 0, 0, 0.0
    for agent, entries in sorted(cost.items()):
        for e in entries:
            calls = e.get("calls") or 0
            i_tok = e.get("in_tok") or 0
            o_tok = e.get("out_tok") or 0
            usd = float(e.get("dollars") or 0.0)
            tot_calls += calls; tot_in += i_tok; tot_out += o_tok; tot_usd += usd
            rows.append(
                f"<tr><td><strong>{html.escape(agent)}</strong></td>"
                f"<td>{html.escape(str(e.get('provider', '—')))}</td>"
                f"<td>{calls}</td><td>{i_tok:,}</td><td>{o_tok:,}</td>"
                f"<td>{(e.get('total_latency_ms') or 0) / 1000:.1f}s</td>"
                f"<td>${usd:.6f}</td></tr>")
    return f"""
<section id="cost">
  <h2>8 · Turn count &amp; cost summary</h2>
  {local}
  <div class="table-scroll"><table>
    <thead><tr><th>agent</th><th>provider</th><th>calls</th><th>tokens in</th>
      <th>tokens out</th><th>latency</th><th>cost</th></tr></thead>
    <tbody>{''.join(rows)}</tbody>
    <tfoot><tr><td colspan="2"><strong>total</strong></td><td>{tot_calls}</td>
      <td>{tot_in:,}</td><td>{tot_out:,}</td><td>—</td>
      <td>${tot_usd:.6f}</td></tr></tfoot>
  </table></div>
  <p class="muted">Attribution is per <code>agent</code> tag, so the browser
     skill is a separately billable line. An <code>extract</code>-path browser
     node makes zero gateway calls and correctly does not appear here.</p>
</section>"""


# ── page assembly ────────────────────────────────────────────────────────────

_CSS = """
*,*::before,*::after{box-sizing:border-box}
body{margin:0;background:#0d1117;color:#e6edf3;
  font:15px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif}
.wrap{max-width:1080px;margin:0 auto;padding:32px 20px 96px}
h1{font-size:26px;margin:0 0 4px}
h2{font-size:19px;margin:0 0 14px;padding-bottom:8px;border-bottom:1px solid #30363d}
h3{font-size:15px;margin:22px 0 8px;font-weight:600}
h4{font-size:13px;margin:16px 0 8px;color:#8b949e;font-weight:600}
section{margin:0 0 44px;scroll-margin-top:16px}
p{margin:0 0 10px}
.muted{color:#8b949e;font-size:13px}
.err{color:#f85149;font-size:13px;font-family:ui-monospace,monospace}
code{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:.9em;
  background:#161b22;border:1px solid #30363d;border-radius:4px;padding:1px 5px}
pre{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:12px;
  overflow-x:auto;font-size:12px;line-height:1.5;max-height:460px}
pre code{background:none;border:none;padding:0}
a{color:#58a6ff}
blockquote.goal{margin:0 0 10px;padding:14px 18px;background:#161b22;
  border-left:3px solid #58a6ff;border-radius:0 8px 8px 0;font-size:16px}
header.top{margin-bottom:28px;padding-bottom:20px;border-bottom:1px solid #30363d}
nav.toc{display:flex;flex-wrap:wrap;gap:8px;margin-top:14px}
nav.toc a{font-size:12px;text-decoration:none;color:#8b949e;background:#161b22;
  border:1px solid #30363d;border-radius:20px;padding:4px 12px}
nav.toc a:hover{color:#e6edf3;border-color:#58a6ff}
.table-scroll{overflow-x:auto;margin:0 0 14px;-webkit-overflow-scrolling:touch}
table{border-collapse:collapse;width:100%;font-size:13px;min-width:520px}
th,td{text-align:left;padding:8px 12px;border-bottom:1px solid #21262d;vertical-align:top}
th{color:#8b949e;font-weight:600;font-size:12px;text-transform:uppercase;
  letter-spacing:.4px;border-bottom:1px solid #30363d}
tfoot td{border-top:1px solid #30363d;border-bottom:none}
table.cmp{background:#0f141a;border:1px solid #30363d;border-radius:8px;min-width:640px}
table.cmp td{font-size:13px}
.pill{display:inline-block;font-size:11px;padding:2px 9px;border-radius:20px;
  border:1px solid #30363d;background:#161b22;color:#8b949e;
  font-family:ui-monospace,monospace}
.pill.complete{color:#3fb950;border-color:#238636;background:#132e1c}
.pill.failed{color:#f85149;border-color:#8b2b2b;background:#3a1618}
.pill.skipped{color:#d29922;border-color:#8a6d1f;background:#2a2520}
.card{background:#161b22;border:1px solid #30363d;border-radius:10px;
  padding:14px 18px;margin:0 0 12px}
.card-head{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:10px}
.card p{margin:0 0 6px;font-size:13px}
.url{word-break:break-all}
.svg-wrap{overflow-x:auto;background:#0f141a;border:1px solid #30363d;
  border-radius:10px;padding:16px;margin-bottom:16px}
.shots{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:16px}
figure{margin:0;background:#161b22;border:1px solid #30363d;border-radius:10px;
  padding:10px;overflow:hidden}
figure img{width:100%;height:auto;border-radius:6px;display:block;
  border:1px solid #30363d}
figcaption{font-size:12px;color:#8b949e;margin-top:8px;
  font-family:ui-monospace,monospace}
details{margin-top:8px}
summary{cursor:pointer;font-size:12px;color:#58a6ff}
details pre{margin-top:8px;max-height:300px}
.answer{background:#161b22;border:1px solid #30363d;border-radius:10px;padding:18px 22px}
.answer table.cmp{background:#0d1117}
.stats{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:16px}
.stat{background:#161b22;border:1px solid #30363d;border-radius:10px;
  padding:12px 20px;min-width:120px}
.stat b{display:block;font-size:22px;color:#58a6ff}
.stat span{font-size:12px;color:#8b949e}
@media(max-width:640px){.wrap{padding:20px 14px 60px}.shots{grid-template-columns:1fr}}
"""

_TOC = [("goal", "1 · Goal"), ("dag", "2 · DAG"), ("path", "3 · Path"),
        ("actions", "4 · Actions"), ("shots", "5 · Screenshots"),
        ("extracted", "6 · Extracted"), ("final", "7 · Table"),
        ("cost", "8 · Cost")]


def build_report(session_id: str, *, use_gateway: bool = True) -> str:
    store = SessionStore(session_id)
    states = store.read_all_nodes()
    if not states:
        raise SystemExit(f"report: no nodes under {SESSIONS_ROOT / session_id}/")

    query = store.read_query()
    try:
        graph = store.read_graph()
    except Exception as e:  # noqa: BLE001 - a corrupt graph must not kill the report
        print(f"[report] WARNING: graph unreadable ({e}); DAG section degraded",
              file=sys.stderr)
        graph = None

    runs = collect_browser_runs(session_id)
    _attach_artifacts_to_nodes(runs, states)
    cost, cost_err = fetch_cost(session_id, enabled=use_gateway)

    toc = "".join(f'<a href="#{i}">{html.escape(t)}</a>' for i, t in _TOC)
    body = "".join([
        section_goal(query, session_id, states),
        section_dag(graph, states),
        section_path(states),
        section_actions(states),
        section_screenshots(runs),
        section_extracted(states),
        section_final(states),
        section_cost(states, cost, cost_err),
    ])
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Replay · {html.escape(session_id)}</title>
<style>{_CSS}</style></head>
<body><div class="wrap">
<header class="top">
  <h1>Browser Comparison Agent — replay</h1>
  <p class="muted">Session <code>{html.escape(session_id)}</code> ·
     generated from <code>state/sessions/{html.escape(session_id)}/</code></p>
  <nav class="toc">{toc}</nav>
</header>
{body}
</div></body></html>"""


def main() -> int:
    ap = argparse.ArgumentParser(description="Render a session as a replay report.")
    ap.add_argument("session_id", nargs="?", help="session id under state/sessions/")
    ap.add_argument("-o", "--output", help="output path (default: <sid>_report.html)")
    ap.add_argument("--no-gateway", action="store_true",
                    help="skip the cost-ledger fetch")
    ap.add_argument("--list", action="store_true", help="list available sessions")
    ap.add_argument("--open", action="store_true", help="open the report when done")
    args = ap.parse_args()

    if args.list or not args.session_id:
        sessions = list_sessions()
        if not sessions:
            print(f"report: no sessions under {SESSIONS_ROOT}/", file=sys.stderr)
            return 2
        print("available sessions:")
        for s in sessions:
            print(f"  {s}")
        return 0

    out = Path(args.output) if args.output else Path(f"{args.session_id}_report.html")
    out.write_text(build_report(args.session_id, use_gateway=not args.no_gateway),
                   encoding="utf-8")
    size_kb = out.stat().st_size / 1024
    print(f"report: wrote {out} ({size_kb:.0f} KB)")
    if args.open:
        webbrowser.open(out.resolve().as_uri())
    return 0


if __name__ == "__main__":
    sys.exit(main())
