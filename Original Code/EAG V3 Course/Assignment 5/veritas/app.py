"""Veritas — Streamlit UI.

    streamlit run app.py

A thin visual layer over orchestrator.py: pick "verify a claim" or
"explore a topic", watch the pipeline run, read the essay it produces.
Nothing here duplicates pipeline logic — Veritas and TopicExplorer do the
work, this file only renders it.
"""

from __future__ import annotations

import html
import json
import os
import re
import time
from pathlib import Path
from typing import Any

import streamlit as st

from orchestrator import ROOT, TopicExplorer, Veritas

RUNS_DIR = ROOT / "runs"

VERDICT_COLORS = {
    "supported": ("#4a7c59", "#e8f0e6"),
    "refuted": ("#b8452f", "#fbe9e4"),
    "mixed": ("#c9902a", "#faf1de"),
    "insufficient_evidence": ("#6b6762", "#efece6"),
    "out_of_scope": ("#6b6762", "#efece6"),
}

# --------------------------------------------------------------------------- #
# page config — must be the first Streamlit call
# --------------------------------------------------------------------------- #

st.set_page_config(
    page_title="Veritas",
    page_icon="📜",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --------------------------------------------------------------------------- #
# styling
# --------------------------------------------------------------------------- #

st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,500;9..144,600&family=Source+Serif+4:opsz,wght@8..60,400;8..60,500&family=DM+Sans:wght@400;500;600&display=swap');

  #MainMenu, footer, header { visibility: hidden; }

  html, body, .stApp {
    background-color: #14120f;
    color: #eee8dc;
    font-family: 'DM Sans', sans-serif;
  }

  h1, h2, h3, .veritas-title { font-family: 'Fraunces', serif !important; letter-spacing: -0.02em; }

  section[data-testid="stSidebar"] {
    background: #0f0d0b;
    border-right: 1px solid #2c2822;
  }
  section[data-testid="stSidebar"] * { font-family: 'DM Sans', sans-serif; }

  .stTextArea textarea, .stTextInput input {
    background: #1c1914 !important;
    color: #eee8dc !important;
    border: 1px solid #35302a !important;
    border-radius: 8px !important;
    font-family: 'DM Sans', sans-serif !important;
  }
  .stTextArea textarea:focus, .stTextInput input:focus {
    border-color: #c9902a !important;
    box-shadow: 0 0 0 1px #c9902a !important;
  }

  .stButton > button {
    background: #c9902a;
    color: #14120f;
    border: none;
    border-radius: 8px;
    font-weight: 600;
    padding: 0.55rem 1.2rem;
    transition: transform 150ms ease, box-shadow 150ms ease;
  }
  .stButton > button:hover {
    transform: translateY(-1px);
    box-shadow: 0 4px 14px rgba(201, 144, 42, 0.35);
    color: #14120f;
  }

  [data-testid="stExpander"] {
    background: #1a1815;
    border: 1px solid #2c2822;
    border-radius: 10px;
  }

  .veritas-eyebrow {
    font-size: 0.72rem;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: #c9902a;
    font-weight: 600;
    margin-bottom: 0.2rem;
  }

  .veritas-paper {
    background: #f6efe0;
    color: #241f18;
    border-radius: 14px;
    padding: 48px 56px;
    margin: 8px 0 28px 0;
    box-shadow: 0 20px 60px rgba(0,0,0,0.35);
  }
  .veritas-paper h1.essay-title {
    font-family: 'Fraunces', serif;
    font-weight: 600;
    font-size: clamp(1.7rem, 2.6vw, 2.4rem);
    line-height: 1.15;
    letter-spacing: -0.02em;
    margin: 0 0 8px 0;
    color: #211c14;
  }
  .veritas-paper .essay-meta {
    font-family: 'DM Sans', sans-serif;
    font-size: 0.82rem;
    color: #6b6250;
    margin-bottom: 28px;
    letter-spacing: 0.02em;
  }
  .veritas-essay-body {
    font-family: 'Source Serif 4', serif;
    font-size: 1.14rem;
    line-height: 1.7;
    color: #241f18;
  }
  .veritas-essay-body h2 {
    font-family: 'Fraunces', serif;
    font-size: 1.35rem;
    font-weight: 600;
    margin: 1.6em 0 0.5em 0;
    color: #241f18;
  }
  .veritas-essay-body h3 {
    font-family: 'Fraunces', serif;
    font-size: 1.12rem;
    font-weight: 600;
    margin: 1.3em 0 0.4em 0;
    color: #241f18;
  }
  .veritas-essay-body p { margin: 0 0 1em 0; }
  .veritas-essay-body .cite {
    color: #9a5a1c;
    font-weight: 600;
    font-size: 0.92em;
    white-space: nowrap;
  }
  .veritas-takeaway {
    margin-top: 28px;
    padding: 18px 22px;
    background: #ece1c8;
    border-left: 4px solid #c9902a;
    border-radius: 6px;
    font-family: 'DM Sans', sans-serif;
    font-size: 0.98rem;
    color: #3a3222;
  }
  .veritas-takeaway .label {
    font-weight: 700;
    text-transform: uppercase;
    font-size: 0.72rem;
    letter-spacing: 0.1em;
    color: #9a5a1c;
    display: block;
    margin-bottom: 6px;
  }

  .veritas-badge {
    display: inline-block;
    padding: 4px 12px;
    border-radius: 999px;
    font-size: 0.78rem;
    font-weight: 700;
    letter-spacing: 0.03em;
    text-transform: uppercase;
  }

  .veritas-source-card {
    padding: 10px 14px;
    margin-bottom: 8px;
    background: #1c1914;
    border: 1px solid #2c2822;
    border-radius: 8px;
  }
  .veritas-source-card a { color: #d9a94a; text-decoration: none; }
  .veritas-source-card a:hover { text-decoration: underline; }
  .veritas-source-meta { color: #8a8377; font-size: 0.82rem; margin-top: 2px; }

  .veritas-run-item {
    padding: 8px 10px;
    border-radius: 6px;
    font-size: 0.85rem;
    margin-bottom: 4px;
  }
</style>
""", unsafe_allow_html=True)

# --------------------------------------------------------------------------- #
# session state (init at top, never inside conditionals)
# --------------------------------------------------------------------------- #

if "result" not in st.session_state:
    st.session_state.result = None
if "subject" not in st.session_state:
    st.session_state.subject = ""
if "mode" not in st.session_state:
    st.session_state.mode = "claim"
if "api_key_input" not in st.session_state:
    st.session_state.api_key_input = ""

# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #


def list_runs() -> list[dict[str, Any]]:
    if not RUNS_DIR.exists():
        return []
    rows = []
    for p in sorted(RUNS_DIR.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True):
        try:
            d = json.loads(p.read_text())
        except Exception:
            continue
        r = d.get("result", {})
        rows.append({
            "path": p,
            "mode": d.get("mode", "claim"),
            "subject": d.get("claim", p.stem),
            "title": r.get("essay_title") or r.get("one_line_answer") or d.get("claim", ""),
            "has_essay": bool(r.get("essay")),
        })
    return rows[:25]


def essay_to_html(essay: str, sources_by_id: dict[str, dict]) -> str:
    """Lightweight markdown-lite -> HTML for the essay body only.

    The compose/compose_topic contracts constrain output to `##`/`###`
    headings and plain paragraphs, so a small hand-rolled converter is
    enough — no need for a markdown dependency.
    """
    escaped = html.escape(essay)
    lines = escaped.split("\n")
    blocks: list[str] = []
    para: list[str] = []

    def flush():
        if para:
            blocks.append("<p>" + " ".join(para) + "</p>")
            para.clear()

    for line in lines:
        stripped = line.strip()
        if not stripped:
            flush()
        elif stripped.startswith("### "):
            flush()
            blocks.append(f"<h3>{stripped[4:]}</h3>")
        elif stripped.startswith("## "):
            flush()
            blocks.append(f"<h2>{stripped[3:]}</h2>")
        else:
            para.append(stripped)
    flush()

    out = "\n".join(blocks)
    out = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", out)

    for sid in sorted(sources_by_id, key=len, reverse=True):
        title = html.escape(sources_by_id[sid].get("title", "") or "")[:140]
        out = out.replace(
            html.escape(sid),
            f'<span class="cite" title="{title}">{html.escape(sid)}</span>',
        )
    return out


def verdict_badge(verdict: str, confidence: str = "") -> str:
    fg, bg = VERDICT_COLORS.get(verdict, ("#6b6762", "#efece6"))
    label = str(verdict).replace("_", " ").upper()
    conf = f" · {confidence} confidence" if confidence else ""
    return (
        f'<span class="veritas-badge" style="color:{fg};background:{bg};">{label}</span>'
        f'<span style="color:#8a8377;font-size:0.85rem;">{conf}</span>'
    )


def run_pipeline(subject: str, mode: str) -> dict[str, Any] | None:
    key_field = "ANTHROPIC_API_KEY" if os.environ.get("ANTHROPIC_API_KEY") else (
        "OPENAI_API_KEY" if os.environ.get("OPENAI_API_KEY") else None
    )
    if not key_field and not st.session_state.api_key_input:
        st.error(
            "No API key found. Set ANTHROPIC_API_KEY / OPENAI_API_KEY in your "
            "environment, or paste one in the sidebar."
        )
        return None
    if st.session_state.api_key_input and not key_field:
        os.environ["ANTHROPIC_API_KEY"] = st.session_state.api_key_input

    log_lines: list[str] = []
    log_box = st.empty()

    def on_log(msg: str) -> None:
        if msg.strip():
            log_lines.append(msg.strip())
            log_box.code("\n".join(log_lines[-16:]), language=None)

    with st.status("Researching — this takes a minute or two...", expanded=True) as status:
        try:
            if mode == "topic":
                result = TopicExplorer(verbose=False, on_log=on_log).run_topic(subject)
            else:
                result = Veritas(verbose=False, on_log=on_log).run(subject)
            status.update(label="Done", state="complete")
        except Exception as exc:
            status.update(label=f"Failed: {exc}", state="error")
            st.exception(exc)
            return None
    log_box.empty()
    return result


def render_result(subject: str, mode: str, result: dict[str, Any]) -> None:
    sources = result.get("sources", [])
    sources_by_id = {s["id"]: s for s in sources}

    essay = result.get("essay", "")
    if essay:
        title = result.get("essay_title") or subject
        kind = "Claim checked" if mode == "claim" else "Topic explored"
        meta_bits = [f"{kind}: {subject}", f"{len(sources)} sources examined"]
        st.markdown(
            f'<div class="veritas-paper">'
            f'<h1 class="essay-title">{html.escape(title)}</h1>'
            f'<div class="essay-meta">{" &nbsp;·&nbsp; ".join(html.escape(m) for m in meta_bits)}</div>'
            f'<div class="veritas-essay-body">{essay_to_html(essay, sources_by_id)}</div>'
            + (
                f'<div class="veritas-takeaway"><span class="label">Takeaway</span>'
                f'{html.escape(result.get("key_takeaway", ""))}</div>'
                if result.get("key_takeaway") else ""
            )
            + "</div>",
            unsafe_allow_html=True,
        )
        st.download_button(
            "Download essay (.md)",
            data=f"# {title}\n\n{essay}\n\n**Takeaway:** {result.get('key_takeaway', '')}\n",
            file_name=re.sub(r"[^a-z0-9]+", "-", title.lower())[:60].strip("-") + ".md",
            mime="text/markdown",
        )
    else:
        st.info(result.get("one_line_answer", "No essay could be produced for this input."))

    cols = st.columns(3 if mode == "claim" else 2)
    if mode == "claim":
        with cols[0]:
            st.markdown('<div class="veritas-eyebrow">Verdict</div>', unsafe_allow_html=True)
            st.markdown(verdict_badge(result.get("verdict", "?"), result.get("confidence", "")),
                        unsafe_allow_html=True)
        with cols[1]:
            audit = result.get("audit", {})
            checks = audit.get("checks", [])
            passed = len([c for c in checks if c.get("result") == "pass"])
            st.markdown('<div class="veritas-eyebrow">Audit</div>', unsafe_allow_html=True)
            st.write(f"{audit.get('verdict', '—')} · {passed}/{len(checks)} checks passed")
        with cols[2]:
            tok = result.get("tokens", {})
            st.markdown('<div class="veritas-eyebrow">Cost</div>', unsafe_allow_html=True)
            st.write(f"{tok.get('input', 0):,} in / {tok.get('output', 0):,} out tokens")
    else:
        with cols[0]:
            tok = result.get("tokens", {})
            st.markdown('<div class="veritas-eyebrow">Cost</div>', unsafe_allow_html=True)
            st.write(f"{tok.get('input', 0):,} in / {tok.get('output', 0):,} out tokens")
        with cols[1]:
            st.markdown('<div class="veritas-eyebrow">Sources</div>', unsafe_allow_html=True)
            st.write(f"{len(sources)} examined")

    # Deterministic citation failures are the one thing a reader must not miss,
    # so they surface as a banner rather than a row inside an audit summary.
    failed_citations = [
        c for c in (result.get("audit", {}).get("checks", [])
                    + [result.get("citation_check")])
        if c and c.get("deterministic") and c.get("result") != "pass"
    ]
    for check in failed_citations:
        st.warning(f"Citation integrity ({check['id']}): {check['reason']}")

    if result.get("open_gaps") or result.get("open_questions"):
        with st.expander("Open gaps / unanswered questions"):
            for g in result.get("open_gaps") or result.get("open_questions"):
                st.markdown(f"- {g}")

    if result.get("audit", {}).get("weakest_link"):
        with st.expander("Weakest link in the argument"):
            st.write(result["audit"]["weakest_link"])

    if sources:
        with st.expander(f"Sources examined ({len(sources)})"):
            for s in sources:
                authors = ", ".join(s.get("authors", [])[:3]) or "Unknown authors"
                st.markdown(
                    f'<div class="veritas-source-card">'
                    f'<a href="{html.escape(s.get("url", "#"))}" target="_blank">{html.escape(s.get("title") or s["id"])}</a>'
                    f'<div class="veritas-source-meta">{html.escape(authors)} '
                    f'· {html.escape(s.get("venue", ""))} {html.escape(str(s.get("year", "")))} '
                    f'· {html.escape(s["id"])}</div></div>',
                    unsafe_allow_html=True,
                )

    with st.expander("Raw trace (debug)"):
        st.json(result)


# --------------------------------------------------------------------------- #
# sidebar
# --------------------------------------------------------------------------- #

with st.sidebar:
    st.markdown('<span class="veritas-title" style="font-size:1.4rem;">Veritas</span>',
                unsafe_allow_html=True)
    st.caption("Scientific essay writer, grounded in cited evidence.")

    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("OPENAI_API_KEY")):
        st.session_state.api_key_input = st.text_input(
            "Anthropic API key (session only)", type="password",
            value=st.session_state.api_key_input,
            help="Not saved to disk. Set ANTHROPIC_API_KEY in your shell to skip this.",
        )

    st.markdown("---")

    mode_label = st.radio(
        "What do you want?",
        ["Verify a claim", "Explore a topic"],
        index=0 if st.session_state.mode == "claim" else 1,
    )
    mode = "claim" if mode_label == "Verify a claim" else "topic"

    placeholder = (
        "e.g. Creatine supplementation improves cognitive performance in "
        "sleep-deprived adults"
        if mode == "claim" else
        "e.g. How does intermittent fasting affect metabolic health?"
    )
    subject = st.text_area("Claim" if mode == "claim" else "Topic",
                            placeholder=placeholder, height=100)

    run_clicked = st.button("Run", use_container_width=True)

    st.markdown("---")
    st.markdown('<div class="veritas-eyebrow">Past essays</div>', unsafe_allow_html=True)
    runs = list_runs()
    if not runs:
        st.caption("No runs yet.")
    for r in runs:
        icon = "✓" if r["has_essay"] else "—"
        label = f'{icon} {r["title"][:42]}'
        if st.button(label, key=f"run_{r['path'].name}", use_container_width=True):
            st.session_state.result = json.loads(r["path"].read_text())["result"]
            st.session_state.subject = r["subject"]
            st.session_state.mode = r["mode"]

# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #

st.markdown('<div class="veritas-eyebrow">Veritas</div>', unsafe_allow_html=True)
st.markdown('<h1 style="margin-top:0;">Evidence, turned into something worth reading</h1>',
            unsafe_allow_html=True)

if run_clicked:
    if not subject.strip():
        st.warning("Enter a claim or topic first.")
    else:
        st.session_state.subject = subject.strip()
        st.session_state.mode = mode
        result = run_pipeline(subject.strip(), mode)
        if result is not None:
            st.session_state.result = result

if st.session_state.result:
    render_result(st.session_state.subject, st.session_state.mode, st.session_state.result)
else:
    st.markdown(
        '<p style="color:#a29c8d;max-width:640px;font-size:1.02rem;line-height:1.6;">'
        "Give it a specific claim to check, or an open topic to explore. "
        "Either way it searches PubMed and arXiv, weighs what it finds, "
        "and writes you an essay to learn from — every empirical sentence "
        "traceable back to a real source.</p>",
        unsafe_allow_html=True,
    )
