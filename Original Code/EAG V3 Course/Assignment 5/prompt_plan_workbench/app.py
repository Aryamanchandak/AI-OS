"""Streamlit interface for evaluating and improving prompts and plans."""

from __future__ import annotations

import difflib
import html
import json

import streamlit as st

from engine import ModelSettings, WorkbenchError, apply_improvements, evaluate_content


st.set_page_config(
    page_title="Prompt & Plan Workbench",
    page_icon="◒",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Fraunces:opsz,wght@9..144,600;9..144,700&display=swap');
:root {
  --ink: #17201c; --forest: #214438; --moss: #47705f; --cream: #f4f0e6;
  --paper: #fffdf7; --line: #d8d2c4; --amber: #d48b38; --muted: #6e746f;
}
html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
.stApp { background: var(--cream); color: var(--ink); }
#MainMenu, footer { visibility: hidden; }
h1, h2, h3 { font-family: 'Fraunces', serif !important; color: var(--ink); letter-spacing: -0.03em; }
h1 { font-size: clamp(2.5rem, 6vw, 5.6rem) !important; line-height: .94 !important; max-width: 920px; }
[data-testid="stSidebar"] { background: #1a2b25; border-right: 0; }
[data-testid="stSidebar"] * { color: #f8f3e8; }
[data-testid="stSidebar"] input { color: #17201c !important; }
.eyebrow { color: var(--moss); font-size: .76rem; font-weight: 700; letter-spacing: .14em; text-transform: uppercase; margin-bottom: .6rem; }
.lede { color: #505a54; font-size: 1.08rem; line-height: 1.7; max-width: 760px; margin: 0 0 2.5rem; }
.workflow { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1px; background: var(--line); border: 1px solid var(--line); margin: 1rem 0 2rem; }
.workflow div { background: var(--paper); padding: 1rem 1.1rem; }
.workflow b { display: block; color: var(--forest); margin-bottom: .2rem; }
.workflow span { color: var(--muted); font-size: .86rem; }
.score-card { background: var(--forest); color: white; padding: 1.6rem; border-radius: 2px; margin-bottom: 1rem; }
.score-card .score { font-family: 'Fraunces', serif; font-size: 4rem; line-height: 1; }
.score-card .label { color: #dce9df; font-size: .8rem; text-transform: uppercase; letter-spacing: .12em; }
.criterion { background: var(--paper); border-left: 4px solid var(--line); padding: 1rem 1.15rem; margin: .6rem 0; }
.criterion.yes { border-color: #3f785f; } .criterion.partial { border-color: var(--amber); } .criterion.no { border-color: #ad5347; }
.criterion-top { display:flex; align-items:center; justify-content:space-between; gap:1rem; }
.criterion-name { font-weight: 700; }.status { font-size:.72rem; font-weight:700; letter-spacing:.09em; text-transform:uppercase; }
.criterion p { color:#535d57; font-size:.91rem; line-height:1.55; margin:.65rem 0 0; }
.priority { display:inline-block; padding:.18rem .5rem; border:1px solid var(--line); color:var(--muted); font-size:.7rem; font-weight:700; letter-spacing:.08em; text-transform:uppercase; }
.diff { background:#17201c; color:#e9ece9; padding:1rem; overflow:auto; white-space:pre-wrap; font: .82rem/1.55 ui-monospace, SFMono-Regular, Menlo, monospace; }
.diff .add { color:#a8e6be; }.diff .del { color:#f0a79e; }
div.stButton > button, div.stDownloadButton > button { border-radius:2px; font-weight:700; min-height:2.8rem; transition:transform .16s ease, box-shadow .16s ease; }
div.stButton > button:hover, div.stDownloadButton > button:hover { transform:translateY(-1px); box-shadow:0 6px 18px rgba(23,32,28,.12); }
textarea:focus, input:focus, button:focus { outline: 2px solid var(--amber) !important; outline-offset: 2px; }
@media (max-width: 760px) { .workflow { grid-template-columns:1fr; } h1 { font-size:2.7rem !important; } }
</style>
""",
    unsafe_allow_html=True,
)

DEFAULTS = {
    "evaluation": None,
    "revision": None,
    "evaluated_content": "",
    "evaluated_context": "",
    "evaluated_kind": "prompt",
    "evaluator_kind": "prompt",
    "evaluator_context": "",
    "evaluator_content": "",
}
for key, value in DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = value


def esc(value: object) -> str:
    return html.escape(str(value))


def settings_panel() -> ModelSettings:
    with st.sidebar:
        st.markdown("## Model settings")
        st.caption("Keys entered here live only in this browser session.")
        provider_label = st.selectbox("Provider", ["Auto (environment)", "OpenAI", "Anthropic"])
        provider = {"Auto (environment)": "auto", "OpenAI": "openai", "Anthropic": "anthropic"}[provider_label]
        model = st.text_input("Model override", placeholder="Leave blank for the default")
        api_key = st.text_input("API key", type="password", placeholder="Optional when set in environment")
        st.divider()
        st.markdown("**Canonical rubric**")
        st.caption("Every evaluation and rewrite reloads ../MAIN_PROMPT.md. Edit that file to change the governing rubric.")
        st.markdown("**Privacy note**")
        st.caption("Your context and content are sent to the selected model provider for evaluation.")
    return ModelSettings(provider=provider, model=model, api_key=api_key)


def render_criterion(item: dict[str, str]) -> None:
    recommendation = ""
    if item["status"] != "yes" and item["recommendation"]:
        recommendation = f"<p><b>Improve:</b> {esc(item['recommendation'])}</p>"
    st.markdown(
        f"""<div class="criterion {esc(item['status'])}">
          <div class="criterion-top"><span class="criterion-name">{esc(item['label'])}</span>
          <span class="status">{esc(item['status'].replace('_', ' '))}</span></div>
          <p>{esc(item['evidence'])}</p>{recommendation}</div>""",
        unsafe_allow_html=True,
    )


def make_diff(before: str, after: str) -> str:
    lines = difflib.unified_diff(before.splitlines(), after.splitlines(), fromfile="original", tofile="optimized", lineterm="")
    rendered = []
    for line in lines:
        klass = "add" if line.startswith("+") and not line.startswith("+++") else "del" if line.startswith("-") and not line.startswith("---") else ""
        rendered.append(f'<span class="{klass}">{esc(line)}</span>')
    return "\n".join(rendered)


settings = settings_panel()

st.markdown('<div class="eyebrow">Evaluation · selection · revision</div>', unsafe_allow_html=True)
st.title("Build clearer prompts. Plan stronger systems.")
st.markdown(
    '<p class="lede">A focused review desk governed by your own evaluation rubric. Add the real-world context, inspect every criterion, then choose exactly which changes the model may apply.</p>',
    unsafe_allow_html=True,
)
st.markdown(
    """<div class="workflow"><div><b>01 · Frame</b><span>Describe where the prompt or plan will operate.</span></div>
    <div><b>02 · Evaluate</b><span>Grade all nine criteria from MAIN_PROMPT.md.</span></div>
    <div><b>03 · Apply</b><span>Tick only the improvements you approve.</span></div></div>""",
    unsafe_allow_html=True,
)

kind = st.radio(
    "What are you reviewing?",
    ["prompt", "plan"],
    horizontal=True,
    format_func=str.title,
    key="evaluator_kind",
)
kind_label = kind.title()
context = st.text_area(
    "Usage context",
    height=140,
    placeholder=(
        "Who will use it? Which model or tools are involved? What outcome matters? "
        "Include constraints, audience, environment, and known failure modes."
    ),
    help="Context is evaluated alongside the content but is not inserted into the revised output unless a selected change requires it.",
    key="evaluator_context",
)
content = st.text_area(
    f"{kind_label} to evaluate",
    height=300,
    placeholder="Paste the complete prompt here…" if kind == "prompt" else "Describe the complete process—from trigger to final validation…",
    key="evaluator_content",
)

if st.button(f"Evaluate {kind}", type="primary", use_container_width=True):
    st.session_state.revision = None
    try:
        with st.spinner(f"Evaluating your {kind} against the canonical rubric…"):
            result = evaluate_content(content, context, kind, settings)
        st.session_state.evaluation = result
        st.session_state.evaluated_content = content
        st.session_state.evaluated_context = context
        st.session_state.evaluated_kind = kind
        for item in result["improvements"]:
            st.session_state[f"pick_{item['id']}"] = item["priority"] == "high"
    except WorkbenchError as exc:
        st.error(str(exc))
    except Exception as exc:
        st.error(f"Unexpected evaluation error: {exc}")

result = st.session_state.evaluation
if result:
    st.divider()
    score_col, summary_col = st.columns([1, 2])
    with score_col:
        st.markdown(
            f'<div class="score-card"><div class="label">Rubric score</div><div class="score">{result["score"]}</div><div>{esc(result["verdict"])}</div></div>',
            unsafe_allow_html=True,
        )
    with summary_col:
        st.subheader("How it fares")
        st.write(result["summary"])
        if result["strengths"]:
            st.markdown("**What already works**")
            for strength in result["strengths"]:
                st.markdown(f"- {strength}")

    evaluation_tab, improvements_tab, output_tab = st.tabs(["Full evaluation", "Proposed improvements", "Optimized output"])
    with evaluation_tab:
        for criterion in result["criteria"]:
            render_criterion(criterion)

    with improvements_tab:
        improvements = result["improvements"]
        if not improvements:
            st.success("No material improvements were proposed.")
        else:
            st.caption("High-priority changes start selected. Untick anything you do not want changed.")
            for item in improvements:
                cols = st.columns([0.12, 0.88])
                with cols[0]:
                    st.checkbox("Select", key=f"pick_{item['id']}", label_visibility="collapsed")
                with cols[1]:
                    st.markdown(f"### {esc(item['title'])} &nbsp; <span class=\"priority\">{esc(item['priority'])}</span>", unsafe_allow_html=True)
                    st.write(item["why"])
                    if item["preview"]:
                        st.caption(f"Preview: {item['preview']}")
            if st.button("Apply selected improvements", type="primary", use_container_width=True):
                selected = [item for item in improvements if st.session_state.get(f"pick_{item['id']}", False)]
                try:
                    with st.spinner("Applying only the approved changes…"):
                        revision = apply_improvements(
                            st.session_state.evaluated_content,
                            st.session_state.evaluated_context,
                            st.session_state.evaluated_kind,
                            selected,
                            settings,
                        )
                    st.session_state.revision = revision
                    st.success("Approved improvements applied. Open “Optimized output” to review and download it.")
                except WorkbenchError as exc:
                    st.error(str(exc))
                except Exception as exc:
                    st.error(f"Unexpected rewrite error: {exc}")

    with output_tab:
        # The evaluation is downloadable as soon as it exists — it is a
        # deliverable in its own right, not a by-product of applying a rewrite.
        st.download_button(
            "Download full evaluation (JSON)",
            json.dumps(result, indent=2, ensure_ascii=False),
            file_name="evaluation.json",
            mime="application/json",
            use_container_width=True,
        )
        revision = st.session_state.revision
        if not revision:
            st.info("Select improvements in the previous tab and apply them. Your original remains untouched.")
        else:
            revised = revision["revised_content"]
            st.text_area("Revised content", value=revised, height=420)
            download_name = f"optimized_{st.session_state.evaluated_kind}.md"
            st.download_button("Download optimized version", revised, file_name=download_name, mime="text/markdown", use_container_width=True)
            with st.expander("See exactly what changed"):
                st.markdown(f'<div class="diff">{make_diff(st.session_state.evaluated_content, revised)}</div>', unsafe_allow_html=True)
            with st.expander("Applied-change receipt"):
                st.json({"applied": revision.get("applied", []), "preserved": revision.get("preserved", [])})
