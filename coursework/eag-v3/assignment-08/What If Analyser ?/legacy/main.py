"""Legacy Streamlit rendering shell for the causal scenario engine.

This was the original UI, predating web/app.py's background-job/SSE setup.
Streamlit's synchronous st.status() gives free live progress without any of
that job-queue machinery, which makes this useful for quickly eyeballing a
pipeline change without touching the FastAPI shell. New deployments should
use web/app.py; this file just delegates orchestration to the same
engine.pipeline.run_pipeline() so both UIs can never disagree on results.

Run:  python -m streamlit run legacy/main.py  (from the project root)
"""

from __future__ import annotations

import html
import os
import sys
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Load GEMINI_API_KEY (and any other vars) from a local .env file, if present.
load_dotenv()

from engine.pipeline import run_pipeline
from engine.presentation import cell, edge_robustness, graph_to_dot
from engine.schema import Graph


# --- UI --------------------------------------------------------------------

# Streamlit executes this file top-to-bottom on every interaction. Page config
# must remain the first Streamlit call.
st.set_page_config(
    page_title="What If — Scenario Intelligence",
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Results live across Streamlit reruns (tabs, expanders, and control changes).
if "analysis_run" not in st.session_state:
    st.session_state.analysis_run = None
if "analysis_error" not in st.session_state:
    st.session_state.analysis_error = ""

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700&family=Newsreader:opsz,wght@6..72,500;6..72,600&display=swap');

    :root {
        --ink: #17212b;
        --ink-soft: #34424e;
        --muted: #6f777d;
        --paper: #f5f1e8;
        --paper-deep: #ece5d7;
        --surface: #fffdf8;
        --line: #d8d1c3;
        --gold: #d7a443;
        --gold-deep: #8b6118;
        --sage: #66816c;
        --sage-pale: #edf4ee;
        --blue: #3e6c89;
        --blue-pale: #ebf2f6;
        --red: #a44d43;
        --red-pale: #f8ece9;
        --shadow: 0 18px 50px rgba(31, 37, 40, 0.08);
    }

    html, body, [class*="css"] {
        font-family: "Manrope", sans-serif;
        color: var(--ink);
    }

    .stApp {
        background:
            radial-gradient(circle at 84% 0%, rgba(215, 164, 67, 0.13), transparent 28rem),
            linear-gradient(rgba(23, 33, 43, 0.025) 1px, transparent 1px),
            linear-gradient(90deg, rgba(23, 33, 43, 0.025) 1px, transparent 1px),
            var(--paper);
        background-size: auto, 32px 32px, 32px 32px, auto;
    }

    [data-testid="stHeader"] {
        background: transparent;
    }

    [data-testid="stToolbar"],
    #MainMenu,
    footer {
        visibility: hidden;
    }

    [data-testid="stAppViewContainer"] > .main .block-container {
        max-width: 1440px;
        padding: 3.25rem clamp(1.25rem, 4vw, 4.5rem) 6rem;
    }

    h1, h2, h3 {
        font-family: "Newsreader", serif !important;
        color: var(--ink);
        letter-spacing: -0.035em;
    }

    h2 {
        font-size: clamp(2rem, 3vw, 3rem) !important;
        line-height: 1.08 !important;
        margin-top: 3.5rem !important;
    }

    p, li, label, [data-testid="stCaptionContainer"] {
        line-height: 1.65;
    }

    .whatif-hero {
        position: relative;
        overflow: hidden;
        min-height: 17rem;
        padding: clamp(2rem, 5vw, 4.5rem);
        border: 1px solid rgba(215, 164, 67, 0.38);
        border-radius: 1.5rem;
        background: var(--ink);
        box-shadow: var(--shadow);
        color: #fff9ec;
        animation: rise-in 420ms ease-out both;
    }

    .whatif-hero::after {
        content: "";
        position: absolute;
        right: -5rem;
        bottom: -9rem;
        width: 24rem;
        height: 24rem;
        border: 1px solid rgba(215, 164, 67, 0.42);
        border-radius: 50%;
        box-shadow: 0 0 0 3rem rgba(215, 164, 67, 0.06),
                    0 0 0 7rem rgba(215, 164, 67, 0.035);
    }

    .whatif-eyebrow,
    .section-kicker {
        margin: 0 0 0.9rem;
        color: var(--gold);
        font-size: 0.72rem;
        font-weight: 700;
        letter-spacing: 0.15em;
        text-transform: uppercase;
    }

    .whatif-hero h1 {
        position: relative;
        z-index: 1;
        max-width: 850px;
        margin: 0;
        color: #fff9ec;
        font-size: clamp(3.25rem, 6.6vw, 6.8rem);
        line-height: 0.92;
        letter-spacing: -0.055em;
    }

    .whatif-hero p:last-child {
        position: relative;
        z-index: 1;
        max-width: 720px;
        margin: 1.6rem 0 0;
        color: #cbd1d3;
        font-size: clamp(1rem, 1.4vw, 1.16rem);
    }

    .whatif-hero em {
        color: var(--gold);
        font-family: "Newsreader", serif;
        font-style: italic;
    }

    [data-testid="stSidebar"] {
        border-right: 1px solid rgba(215, 164, 67, 0.2);
        background: var(--ink);
    }

    [data-testid="stSidebar"] > div:first-child {
        padding: 2rem 1.4rem;
    }

    [data-testid="stSidebar"] * {
        color: #f8f3e9;
    }

    [data-testid="stSidebar"] .sidebar-brand {
        display: flex;
        gap: 0.75rem;
        align-items: center;
        margin-bottom: 2.25rem;
    }

    .brand-mark {
        display: grid;
        width: 2.35rem;
        height: 2.35rem;
        place-items: center;
        border: 1px solid rgba(215, 164, 67, 0.7);
        border-radius: 50%;
        color: var(--gold);
        font-family: "Newsreader", serif;
        font-size: 1.3rem;
    }

    .brand-name {
        color: #fff9ec;
        font-size: 1rem;
        font-weight: 700;
        letter-spacing: -0.02em;
    }

    .brand-sub {
        color: #8f9ba2;
        font-size: 0.7rem;
        letter-spacing: 0.08em;
        text-transform: uppercase;
    }

    [data-testid="stSidebar"] label {
        color: #d9dedf !important;
        font-size: 0.78rem;
        font-weight: 700;
        letter-spacing: 0.05em;
        text-transform: uppercase;
    }

    [data-testid="stSidebar"] textarea {
        min-height: 9rem;
        border: 1px solid #46525b;
        border-radius: 0.85rem;
        background: #202c36;
        color: #fff9ec;
        line-height: 1.55;
    }

    [data-testid="stSidebar"] textarea:focus {
        border-color: var(--gold);
        box-shadow: 0 0 0 3px rgba(215, 164, 67, 0.18);
    }

    [data-testid="stSidebar"] textarea::placeholder {
        color: #82909a;
    }

    [data-testid="stSidebar"] .stButton > button {
        min-height: 3rem;
        border: 1px solid var(--gold);
        border-radius: 999px;
        background: var(--gold);
        color: var(--ink);
        font-weight: 800;
        letter-spacing: 0.015em;
        transition: transform 160ms ease, box-shadow 160ms ease, background 160ms ease;
    }

    [data-testid="stSidebar"] .stButton > button:hover {
        border-color: #edc977;
        background: #edc977;
        color: var(--ink);
        box-shadow: 0 10px 24px rgba(215, 164, 67, 0.24);
        transform: translateY(-1px);
    }

    [data-testid="stSidebar"] .stButton > button:focus-visible {
        outline: 3px solid rgba(255, 249, 236, 0.7);
        outline-offset: 3px;
    }

    .brief-card {
        margin-top: 1.5rem;
        padding: 1rem;
        border: 1px solid #35434d;
        border-radius: 1rem;
        background: rgba(255, 255, 255, 0.035);
    }

    .brief-card-title {
        margin-bottom: 0.8rem;
        color: var(--gold);
        font-size: 0.68rem;
        font-weight: 800;
        letter-spacing: 0.13em;
        text-transform: uppercase;
    }

    .brief-row {
        display: flex;
        justify-content: space-between;
        gap: 1rem;
        padding: 0.62rem 0;
        border-top: 1px solid rgba(255, 255, 255, 0.08);
        color: #98a4aa;
        font-size: 0.76rem;
    }

    .brief-row strong {
        color: #f8f3e9;
        font-weight: 600;
        text-align: right;
    }

    [data-testid="stAlert"] {
        border-radius: 0.9rem;
    }

    .result-intro {
        display: flex;
        justify-content: space-between;
        gap: 2rem;
        align-items: end;
        margin: 4.2rem 0 1.2rem;
    }

    .result-intro h2 {
        margin: 0 !important;
    }

    .result-intro p {
        max-width: 590px;
        margin: 0;
        color: var(--muted);
    }

    .metric-ribbon {
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        overflow: hidden;
        margin: 1.25rem 0 2rem;
        border: 1px solid var(--line);
        border-radius: 1rem;
        background: rgba(255, 253, 248, 0.86);
        box-shadow: 0 10px 30px rgba(31, 37, 40, 0.045);
    }

    .metric-ribbon > div {
        padding: 1rem 1.15rem;
        border-left: 1px solid var(--line);
    }

    .metric-ribbon > div:first-child {
        border-left: 0;
    }

    .metric-label {
        color: var(--muted);
        font-size: 0.66rem;
        font-weight: 700;
        letter-spacing: 0.1em;
        text-transform: uppercase;
    }

    .metric-value {
        margin-top: 0.2rem;
        color: var(--ink);
        font-family: "Newsreader", serif;
        font-size: 1.45rem;
        font-weight: 600;
    }

    .matrix-shell {
        overflow-x: auto;
        margin-bottom: 0.6rem;
        border: 1px solid var(--line);
        border-radius: 1rem;
        background: var(--surface);
        box-shadow: var(--shadow);
    }

    .scenario-matrix {
        width: 100%;
        min-width: 760px;
        border-collapse: collapse;
    }

    .scenario-matrix th {
        padding: 0.95rem 1rem;
        border-bottom: 1px solid var(--line);
        background: #efe9dc;
        color: var(--ink-soft);
        font-size: 0.68rem;
        font-weight: 800;
        letter-spacing: 0.08em;
        text-align: left;
        text-transform: uppercase;
    }

    .scenario-matrix td {
        padding: 1rem;
        border-top: 1px solid #e8e2d6;
        color: var(--ink-soft);
        font-size: 0.82rem;
        vertical-align: middle;
    }

    .scenario-matrix tbody tr:first-child td {
        border-top: 0;
    }

    .scenario-matrix tbody tr:hover {
        background: #fbf8f1;
    }

    .scenario-matrix td:first-child {
        min-width: 240px;
        color: var(--ink);
        font-weight: 700;
    }

    .impact {
        display: inline-flex;
        min-width: 4.1rem;
        justify-content: center;
        padding: 0.4rem 0.58rem;
        border-radius: 999px;
        font-weight: 800;
        letter-spacing: 0.04em;
    }

    .impact-up {
        background: var(--blue-pale);
        color: var(--blue);
    }

    .impact-down {
        background: var(--red-pale);
        color: var(--red);
    }

    .impact-flat {
        background: #efede7;
        color: #6f777d;
    }

    .impact-contested {
        background: #fff3d6;
        color: var(--gold-deep);
    }

    .matrix-legend {
        margin-bottom: 2.2rem;
        color: var(--muted);
        font-size: 0.75rem;
    }

    [data-testid="stVerticalBlockBorderWrapper"] {
        border-color: var(--line);
        border-radius: 1.15rem;
        background: rgba(255, 253, 248, 0.88);
        box-shadow: 0 14px 36px rgba(31, 37, 40, 0.055);
        transition: border-color 170ms ease, box-shadow 170ms ease, transform 170ms ease;
    }

    [data-testid="stVerticalBlockBorderWrapper"]:hover {
        border-color: #c8b784;
        box-shadow: 0 18px 42px rgba(31, 37, 40, 0.085);
        transform: translateY(-2px);
    }

    .scenario-index {
        display: inline-flex;
        align-items: center;
        gap: 0.45rem;
        color: var(--gold-deep);
        font-size: 0.67rem;
        font-weight: 800;
        letter-spacing: 0.11em;
        text-transform: uppercase;
    }

    .scenario-index::before {
        content: "";
        width: 1.15rem;
        height: 1px;
        background: var(--gold);
    }

    .scenario-title {
        margin: 0.45rem 0 0.9rem;
        color: var(--ink);
        font-family: "Newsreader", serif;
        font-size: clamp(1.35rem, 2vw, 1.85rem);
        font-weight: 600;
        line-height: 1.15;
        letter-spacing: -0.025em;
    }

    .scenario-narrative {
        min-height: 8.2rem;
        color: var(--ink-soft);
        font-size: 0.9rem;
        line-height: 1.68;
    }

    .outcome-strip {
        display: flex;
        flex-wrap: wrap;
        gap: 0.45rem;
        margin: 1rem 0 0.35rem;
    }

    .outcome-chip {
        padding: 0.38rem 0.55rem;
        border: 1px solid var(--line);
        border-radius: 0.55rem;
        background: #f7f3eb;
        color: var(--ink-soft);
        font-size: 0.68rem;
    }

    .outcome-chip strong {
        margin-left: 0.25rem;
        color: var(--ink);
    }

    [data-testid="stExpander"] {
        overflow: hidden;
        border: 1px solid var(--line);
        border-radius: 0.8rem;
        background: rgba(255, 253, 248, 0.72);
    }

    [data-testid="stExpander"] summary {
        font-size: 0.82rem;
        font-weight: 700;
    }

    [data-testid="stTabs"] [data-baseweb="tab-list"] {
        gap: 0.3rem;
    }

    [data-testid="stTabs"] button {
        border-radius: 999px;
        color: var(--muted);
        font-weight: 700;
    }

    [data-testid="stTabs"] button[aria-selected="true"] {
        background: var(--ink);
        color: #fff9ec;
    }

    [data-testid="stGraphVizChart"] {
        overflow: hidden;
        padding: 1.2rem;
        border: 1px solid var(--line);
        border-radius: 1rem;
        background: var(--surface);
        box-shadow: var(--shadow);
    }

    [data-testid="stStatusWidget"] {
        border: 1px solid var(--line);
        border-radius: 1rem;
        background: rgba(255, 253, 248, 0.9);
    }

    .empty-state {
        display: grid;
        min-height: 19rem;
        margin-top: 1.4rem;
        place-items: center;
        border: 1px dashed #c9bfad;
        border-radius: 1.25rem;
        background: rgba(255, 253, 248, 0.54);
        text-align: center;
    }

    .empty-state-mark {
        color: var(--gold);
        font-family: "Newsreader", serif;
        font-size: 2.3rem;
    }

    .empty-state h3 {
        margin: 0.3rem 0;
        font-size: 1.55rem;
    }

    .empty-state p {
        max-width: 460px;
        margin: 0;
        color: var(--muted);
        font-size: 0.9rem;
    }

    .artifact-grid {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 0.8rem;
        margin: 0.8rem 0 1.2rem;
    }

    .artifact-card {
        padding: 1rem;
        border: 1px solid var(--line);
        border-radius: 0.9rem;
        background: var(--surface);
    }

    .artifact-card h4 {
        margin: 0.45rem 0 0.35rem;
        font-family: "Manrope", sans-serif !important;
        font-size: 0.88rem;
        letter-spacing: -0.01em;
    }

    .artifact-card p {
        margin: 0;
        color: var(--muted);
        font-size: 0.76rem;
        line-height: 1.55;
    }

    .artifact-meta, .evidence-badge {
        display: inline-flex;
        padding: 0.25rem 0.48rem;
        border-radius: 999px;
        background: #efe9dc;
        color: var(--ink-soft);
        font-size: 0.62rem;
        font-weight: 800;
        letter-spacing: 0.06em;
        text-transform: uppercase;
    }

    .badge-supported, .badge-fact { background: var(--sage-pale); color: #35513c; }
    .badge-mixed, .badge-inference { background: #fff3d6; color: var(--gold-deep); }
    .badge-contradicted { background: var(--red-pale); color: var(--red); }
    .badge-assumption, .badge-unverified { background: #efede7; color: #697178; }
    .badge-forecast { background: var(--blue-pale); color: var(--blue); }

    .debate-line {
        padding: 0.75rem 0;
        border-top: 1px solid var(--line);
    }

    .debate-line:first-child { border-top: 0; }

    @keyframes rise-in {
        from { opacity: 0; transform: translateY(12px); }
        to { opacity: 1; transform: translateY(0); }
    }

    @media (max-width: 900px) {
        [data-testid="stAppViewContainer"] > .main .block-container {
            padding: 2rem 1rem 4rem;
        }

        .whatif-hero {
            min-height: auto;
            padding: 2.2rem 1.5rem;
        }

        .result-intro {
            display: block;
            margin-top: 3rem;
        }

        .result-intro p {
            margin-top: 0.8rem;
        }

        .metric-ribbon {
            grid-template-columns: repeat(2, minmax(0, 1fr));
        }

        .artifact-grid { grid-template-columns: 1fr; }

        .metric-ribbon > div:nth-child(3) {
            border-top: 1px solid var(--line);
            border-left: 0;
        }

        .metric-ribbon > div:nth-child(4) {
            border-top: 1px solid var(--line);
        }
    }

    @media (max-width: 520px) {
        .whatif-hero h1 {
            font-size: 3rem;
        }

        .metric-ribbon {
            grid-template-columns: 1fr;
        }

        .metric-ribbon > div {
            border-top: 1px solid var(--line);
            border-left: 0;
        }

        .metric-ribbon > div:first-child {
            border-top: 0;
        }
    }

    @media (prefers-reduced-motion: reduce) {
        *, *::before, *::after {
            scroll-behavior: auto !important;
            animation-duration: 0.01ms !important;
            animation-iteration-count: 1 !important;
            transition-duration: 0.01ms !important;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def _impact_class(node) -> str:
    """Return the presentation class for one resolved outcome."""
    if node.contested:
        return "impact-contested"
    if node.sign > 0:
        return "impact-up"
    if node.sign < 0:
        return "impact-down"
    return "impact-flat"


def render_comparison_matrix(
    names: list[str],
    resolved: list[Graph],
    outcome_nodes: list,
) -> None:
    """Render the four-world outcome comparison as an accessible HTML table."""
    header_cells = "".join(
        f"<th scope='col'>{html.escape(node.label)}</th>"
        for node in outcome_nodes
    )
    body_rows = []
    for name, resolved_graph in zip(names, resolved):
        by_id = {node.id: node for node in resolved_graph.nodes}
        outcome_cells = "".join(
            (
                "<td><span class='impact "
                f"{_impact_class(by_id[node.id])}'>"
                f"{html.escape(cell(by_id[node.id]))}</span></td>"
            )
            for node in outcome_nodes
        )
        body_rows.append(
            "<tr>"
            f"<td>{html.escape(name)}</td>"
            f"{outcome_cells}"
            "</tr>"
        )

    st.markdown(
        """
        <div class="matrix-shell" role="region" aria-label="Scenario outcome comparison" tabindex="0">
          <table class="scenario-matrix">
            <thead>
              <tr><th scope="col">Scenario</th>"""
        + header_cells
        + """</tr>
            </thead>
            <tbody>"""
        + "".join(body_rows)
        + """</tbody>
          </table>
        </div>
        <div class="matrix-legend">
          ↑↑ high up · ↑ up · ▴ slight up · · flat · ▾ slight down · ↓ down ·
          ↓↓ high down · ⚠ contested
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_scenario_card(
    index: int,
    name: str,
    narrative: str,
    resolved_graph: Graph,
    outcome_nodes: list,
) -> None:
    """Render a polished scenario summary while retaining auditable traces."""
    by_id = {node.id: node for node in resolved_graph.nodes}
    chips = "".join(
        (
            "<span class='outcome-chip'>"
            f"{html.escape(outcome.label)} "
            f"<strong>{html.escape(cell(by_id[outcome.id]))}</strong>"
            "</span>"
        )
        for outcome in outcome_nodes
    )

    with st.container(border=True):
        st.markdown(
            f"""
            <div class="scenario-index">Scenario {index:02d}</div>
            <div class="scenario-title">{html.escape(name)}</div>
            <div class="scenario-narrative">{html.escape(narrative)}</div>
            <div class="outcome-strip">{chips}</div>
            """,
            unsafe_allow_html=True,
        )
        with st.expander("Inspect outcome reasoning"):
            for outcome in outcome_nodes:
                node = by_id[outcome.id]
                st.markdown(f"**{outcome.label} — {cell(node)}**")
                if node.trace:
                    for line in node.trace:
                        st.code(line, language=None)
                else:
                    st.caption("No upstream drivers (root or unforced).")


def render_research_artifacts(sources, claims, research_error: str) -> None:
    """Render traceable source cards and the classified evidence ledger."""
    st.subheader("Research grounding")
    if research_error:
        st.warning(
            "Research degraded gracefully: "
            f"{research_error}. The graph was built from the brief alone."
        )
    if not sources:
        st.caption("No retrieved sources are attached to this run.")
        return

    source_by_id = {source.id: source for source in sources}
    source_cards = []
    for source in sources:
        source_cards.append(
            f"""
            <article class="artifact-card">
              <span class="artifact-meta">{html.escape(source.authority)} authority</span>
              <span class="artifact-meta">{html.escape(source.recency)} freshness</span>
              <span class="artifact-meta">{html.escape(source.relevance)} relevance</span>
              <h4>{html.escape(source.title)}</h4>
              <p>{html.escape(source.publisher)} · retrieved
              {html.escape(source.retrieved_at[:10])}</p>
              <p><a href="{html.escape(source.url, quote=True)}" target="_blank"
              rel="noopener noreferrer">Open source ↗</a></p>
            </article>
            """
        )
    with st.expander(f"Sources · {len(sources)} retrieved", expanded=False):
        st.markdown(
            '<div class="artifact-grid">' + "".join(source_cards) + "</div>",
            unsafe_allow_html=True,
        )

    with st.expander(f"Evidence ledger · {len(claims)} claims", expanded=False):
        for claim in claims:
            source = source_by_id.get(claim.source_id)
            source_name = source.title if source else claim.source_id
            st.markdown(
                f"<span class='evidence-badge badge-{html.escape(claim.claim_type)}'>"
                f"{html.escape(claim.claim_type)}</span> "
                f"<span class='evidence-badge'>{html.escape(claim.stance)}</span>",
                unsafe_allow_html=True,
            )
            st.markdown(f"**{claim.text}**")
            st.caption(f"{source_name} · {claim.confidence} confidence · {claim.id}")
            st.code(claim.supporting_passage, language=None)


def render_debate_artifacts(critique, report, diff, debate_error: str) -> None:
    """Expose the one-round challenge and deterministic graph changes."""
    st.subheader("Analyst debate")
    if debate_error:
        st.warning(debate_error)
    role = critique.role if critique else "unavailable"
    st.markdown(
        f"<span class='evidence-badge'>{html.escape(role)} critic</span>",
        unsafe_allow_html=True,
    )
    if critique:
        st.write(critique.summary)
        with st.expander(f"Structured findings · {len(critique.findings)}"):
            if not critique.findings:
                st.caption("No material finding was returned.")
            for finding in critique.findings:
                st.markdown(
                    f"**{finding.src} → {finding.dst} · {finding.severity}**"
                )
                st.write(finding.issue)
                st.caption(f"Recommended: {finding.recommendation}")

    decision_tabs = st.tabs(["Adjudication", "Graph diff", "Unresolved"])
    with decision_tabs[0]:
        for label, values in (
            ("Accepted", report.accepted),
            ("Changed", report.changed),
            ("Rejected", report.rejected),
        ):
            st.markdown(f"**{label}**")
            if values:
                for value in values:
                    st.markdown(f"- {value}")
            else:
                st.caption("None recorded.")
    with decision_tabs[1]:
        for label, values in (
            ("Added", diff.added),
            ("Removed", diff.removed),
            ("Changed", diff.changed),
        ):
            st.markdown(f"**{label}**")
            if values:
                for value in values:
                    st.markdown(f"- {value}")
            else:
                st.caption("None.")
    with decision_tabs[2]:
        if report.unresolved:
            for value in report.unresolved:
                st.markdown(f"- {value}")
        else:
            st.caption("No unresolved disagreements were recorded.")


st.markdown(
    """
    <section class="whatif-hero">
      <p class="whatif-eyebrow">Causal scenario intelligence</p>
      <h1>Map the forces.<br>See the <em>futures.</em></h1>
      <p>
        Turn one uncertain situation into four transparent worlds—each grounded
        in the same causal structure and resolved through deterministic logic.
      </p>
    </section>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.markdown(
        """
        <div class="sidebar-brand">
          <span class="brand-mark">◈</span>
          <span>
            <div class="brand-name">What If</div>
            <div class="brand-sub">Scenario analyser</div>
          </span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown('<p class="section-kicker">Analysis brief</p>', unsafe_allow_html=True)
    situation = st.text_area(
        "Situation to analyse",
        placeholder="e.g. RBI cuts the repo rate by 50bp",
        help="Describe one intervention, decision, or external change.",
    )
    analysis_mode = st.selectbox(
        "Research depth",
        options=("Quick", "Deep"),
        help="Quick retrieves up to 20 sources; Deep retrieves up to 40.",
    )
    run = st.button("Build scenario map", type="primary", width="stretch")
    st.markdown(
        """
        <div class="brief-card">
          <div class="brief-card-title">Method at a glance</div>
          <div class="brief-row"><span>Worlds</span><strong>4 scenarios</strong></div>
          <div class="brief-row"><span>Uncertainties</span><strong>2 toggles</strong></div>
          <div class="brief-row"><span>Research</span><strong>Evidence + counterevidence</strong></div>
          <div class="brief-row"><span>Challenge</span><strong>One critic · one round</strong></div>
          <div class="brief-row"><span>Calculation</span><strong>Deterministic</strong></div>
          <div class="brief-row"><span>Auditability</span><strong>Source-linked edges</strong></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

if not (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")):
    st.warning(
        "No Gemini API key was found. Add `GEMINI_API_KEY` and restart the app "
        "before building a scenario map."
    )

if run and not situation.strip():
    st.info("Type a situation first.")

if run and situation.strip():
    pipeline_status = st.status("Assembling the decision map", expanded=True)
    try:
        def report_progress(_step_id: str, message: str) -> None:
            pipeline_status.write(message)

        completed = run_pipeline(
            situation,
            analysis_mode,
            on_progress=report_progress,
        )
        # Assignment happens only after full success, preserving the last good
        # result if graph construction or synthesis fails.
        st.session_state.analysis_run = completed
        st.session_state.analysis_error = ""
        pipeline_status.update(
            label="Grounded scenario map ready",
            state="complete",
            expanded=False,
        )
    except Exception as exc:
        # Do not overwrite a completed run. It remains visible below.
        st.session_state.analysis_error = str(exc)
        pipeline_status.update(
            label="The new analysis could not be completed",
            state="error",
            expanded=True,
        )

if st.session_state.analysis_error:
    st.error(
        "The latest run failed, so the previous completed analysis was kept. "
        + st.session_state.analysis_error
    )

analysis = st.session_state.analysis_run
if analysis:
    graph = analysis["graph"]
    assignments = analysis["assignments"]
    names = analysis["names"]
    resolved = analysis["resolved"]
    narratives = analysis["narratives"]
    outcome_nodes_order = [
        node for node in graph.nodes if node.node_type == "outcome"
    ]

    st.markdown(
        """
        <div class="result-intro">
          <div>
            <p class="section-kicker">Decision landscape</p>
            <h2>Four worlds, one challenged causal spine</h2>
          </div>
          <p>
            Retrieved claims ground the builder, one selected critic challenges
            it, and a single adjudication round repairs it before propagation.
          </p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    supported_edges = sum(
        edge.evidence_status == "supported" for edge in graph.edges
    )
    st.markdown(
        f"""
        <div class="metric-ribbon">
          <div><div class="metric-label">Sources</div><div class="metric-value">{len(analysis["sources"])}</div></div>
          <div><div class="metric-label">Claims</div><div class="metric-value">{len(analysis["claims"])}</div></div>
          <div><div class="metric-label">Causal edges</div><div class="metric-value">{len(graph.edges)}</div></div>
          <div><div class="metric-label">Verified support</div><div class="metric-value">{supported_edges}</div></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    render_comparison_matrix(names, resolved, outcome_nodes_order)

    st.subheader("Scenario briefs")
    card_columns = st.columns(2, gap="large")
    for index, (name, narrative, resolved_graph) in enumerate(
        zip(names, narratives, resolved), start=1
    ):
        with card_columns[(index - 1) % 2]:
            render_scenario_card(
                index, name, narrative, resolved_graph, outcome_nodes_order
            )

    render_research_artifacts(
        analysis["sources"],
        analysis["claims"],
        analysis["research_error"],
    )
    render_debate_artifacts(
        analysis["critique"],
        analysis["report"],
        analysis["diff"],
        analysis["debate_error"],
    )
    if analysis["verification_error"]:
        st.warning(
            "Load-bearing verification remained unverified: "
            + analysis["verification_error"]
        )

    st.subheader("Causal model")
    diagram_tab, details_tab = st.tabs(["Visual map", "Audit details"])
    with diagram_tab:
        st.graphviz_chart(graph_to_dot(graph), width="stretch")
        st.caption(
            "Dark: intervention · White: intermediate · Sage: outcome · "
            "Gold dashed: unknown · Blue: positive · Red: inverse"
        )
    with details_tab:
        st.markdown("**Nodes**")
        st.dataframe(
            pd.DataFrame(
                [
                    {"id": node.id, "type": node.node_type, "label": node.label}
                    for node in graph.nodes
                ]
            ).set_index("id"),
            width="stretch",
        )
        st.markdown("**Edges, evidence, and mechanisms**")
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "from": edge.src,
                        "to": edge.dst,
                        "sign": f"{edge.sign:+d}",
                        "strength": edge.strength,
                        "confidence": edge.confidence,
                        "lag": edge.time_lag,
                        "evidence": edge.evidence_status,
                        "supporting claims": ", ".join(
                            edge.supporting_claim_ids
                        ),
                        "mechanism": edge.mechanism,
                    }
                    for edge in graph.edges
                ]
            ),
            width="stretch",
            hide_index=True,
        )
        st.markdown("**Unknowns**")
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "id": unknown.id,
                        "affects": unknown.affects_node_id,
                        "question": unknown.question,
                    }
                    for unknown in graph.unknowns
                ]
            ).set_index("id"),
            width="stretch",
        )

    st.subheader("Structural sensitivity")
    with st.expander("Open exact-edge audit"):
        st.caption(
            "Each named edge is flipped once and all four worlds are re-run. "
            "Only links that change a conclusion are verification targets."
        )
        robustness = edge_robustness(graph, assignments[0])
        if robustness.empty:
            st.info("No single edge flip changes an outcome in this scenario.")
        else:
            st.dataframe(robustness, width="stretch", hide_index=True)
else:
    st.markdown(
        """
        <div class="empty-state">
          <div>
            <div class="empty-state-mark">◈</div>
            <h3>Your scenario map starts with one situation.</h3>
            <p>
              Use the analysis brief at left. The engine will research, challenge,
              and expose the causal reasoning behind every outcome.
            </p>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
