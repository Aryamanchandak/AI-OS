"""Chat-first prompt and plan constructor for the workbench."""

from __future__ import annotations

import html
import json

import streamlit as st

from engine import MAX_CONSTRUCTOR_QUESTIONS, ModelSettings, WorkbenchError, converse


st.set_page_config(
    page_title="Constructor · Prompt & Plan Workbench",
    page_icon="✦",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Fraunces:opsz,wght@9..144,600;9..144,700&display=swap');
:root {
  --ink:#17201c; --forest:#214438; --moss:#47705f; --cream:#f4f0e6;
  --paper:#fffdf7; --line:#d8d2c4; --amber:#d48b38; --muted:#6e746f;
}
html, body, [class*="css"] { font-family:'DM Sans', sans-serif; }
.stApp { background:var(--cream); color:var(--ink); }
#MainMenu, footer { visibility:hidden; }
h1, h2, h3 { font-family:'Fraunces', serif !important; color:var(--ink); letter-spacing:-.03em; }
h1 { font-size:clamp(2.5rem, 5vw, 4.8rem) !important; line-height:.98 !important; }
[data-testid="stSidebar"] { background:#1a2b25; border-right:0; }
[data-testid="stSidebar"] * { color:#f8f3e8; }
[data-testid="stSidebar"] input { color:#17201c !important; }
.eyebrow { color:var(--moss); font-size:.76rem; font-weight:700; letter-spacing:.14em; text-transform:uppercase; margin-bottom:.6rem; }
.lede { color:#505a54; font-size:1.08rem; line-height:1.7; max-width:760px; margin-bottom:2rem; }
.empty-state { border:1px solid var(--line); background:var(--paper); padding:2rem; margin:1rem 0; }
.empty-state b { color:var(--forest); display:block; font-size:1.1rem; margin-bottom:.35rem; }
.draft-card { background:#243a32; color:#f8f3e8; border-left:4px solid var(--amber); padding:1.25rem; margin:.75rem 0 1rem; white-space:pre-wrap; line-height:1.6; }
.draft-label { color:#d8b17a; font-size:.7rem; font-weight:700; letter-spacing:.12em; text-transform:uppercase; }
[data-testid="stChatMessage"] { background:var(--paper); border:1px solid var(--line); border-radius:2px; padding:.35rem .8rem; margin-bottom:.7rem; }
div.stButton > button { border-radius:2px; font-weight:700; min-height:2.8rem; transition:transform .16s ease, box-shadow .16s ease; }
div.stButton > button:hover { transform:translateY(-1px); box-shadow:0 6px 18px rgba(23,32,28,.12); }
textarea:focus, input:focus, button:focus { outline:2px solid var(--amber) !important; outline-offset:2px; }
@keyframes enter { from { opacity:0; transform:translateY(8px); } to { opacity:1; transform:translateY(0); } }
.empty-state, .draft-card, [data-testid="stChatMessage"] { animation:enter .28s ease-out both; }
</style>
""",
    unsafe_allow_html=True,
)

DEFAULTS = {
    "constructor_history": [],
    "constructor_result": None,
    "evaluator_kind": "prompt",
    "evaluator_content": "",
    "evaluator_context": "",
}
for key, value in DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = value


def settings_panel() -> ModelSettings:
    with st.sidebar:
        st.markdown("## Draft so far")
        result = st.session_state.constructor_result
        if result and result["notes"]:
            kind = result["draft_kind"] or "In discovery"
            st.markdown(f"**{html.escape(str(kind).title())}**")
            st.caption(result["notes"])
        else:
            st.caption("Your decisions will collect here as the interview develops.")

        turns = sum(message["role"] == "assistant" for message in st.session_state.constructor_history)
        st.progress(min(turns / MAX_CONSTRUCTOR_QUESTIONS, 1.0), text=f"{turns} of {MAX_CONSTRUCTOR_QUESTIONS} questions used")
        if st.button("Start over", use_container_width=True):
            st.session_state.constructor_history = []
            st.session_state.constructor_result = None
            st.rerun()

        st.divider()
        st.markdown("## Model settings")
        provider_label = st.selectbox("Provider", ["Auto (environment)", "OpenAI", "Anthropic"], key="constructor_provider")
        provider = {"Auto (environment)": "auto", "OpenAI": "openai", "Anthropic": "anthropic"}[provider_label]
        model = st.text_input("Model override", placeholder="Leave blank for the default", key="constructor_model")
        api_key = st.text_input("API key", type="password", placeholder="Optional when set in environment", key="constructor_api_key")
        st.caption("Answers are sent to the selected provider. Keys remain only in this browser session.")
    return ModelSettings(provider=provider, model=model, api_key=api_key)


def visible_assistant_message(content: str) -> str:
    try:
        parsed = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return content
    return str(parsed.get("question") or "Draft ready.")


settings = settings_panel()

st.markdown('<div class="eyebrow">Discover · clarify · construct</div>', unsafe_allow_html=True)
st.title("Turn a rough goal into a working brief.")
st.markdown(
    '<p class="lede">Describe what you want to accomplish. The Constructor will ask one focused question at a time, capture the decisions, and hand a complete prompt or plan to the evaluator.</p>',
    unsafe_allow_html=True,
)

history = st.session_state.constructor_history
if not history:
    st.markdown(
        '<div class="empty-state"><b>Start with the messy version.</b>You do not need the right terminology or a complete specification. A sentence about the outcome you want is enough.</div>',
        unsafe_allow_html=True,
    )

for message in history:
    with st.chat_message(message["role"]):
        st.write(message["content"] if message["role"] == "user" else visible_assistant_message(message["content"]))

result = st.session_state.constructor_result
if result and result["ready"]:
    st.success("Your draft is ready to evaluate.")
    st.markdown(f'<div class="draft-label">Complete {html.escape(result["draft_kind"])}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="draft-card">{html.escape(result["draft_content"])}</div>', unsafe_allow_html=True)
    with st.expander("Evaluator context"):
        st.write(result["draft_context"] or "No additional usage context was distilled.")
    if st.button("Send to Evaluator →", type="primary", use_container_width=True):
        st.session_state.evaluator_kind = result["draft_kind"]
        st.session_state.evaluator_content = result["draft_content"]
        st.session_state.evaluator_context = result["draft_context"]
        st.session_state.evaluation = None
        st.session_state.revision = None
        st.switch_page("app.py")
else:
    user_message = st.chat_input("What do you want this prompt or plan to achieve?")
    if user_message:
        history.append({"role": "user", "content": user_message})
        try:
            with st.spinner("Finding the most useful next question…"):
                reply = converse(history, settings)
            history.append({"role": "assistant", "content": json.dumps(reply, ensure_ascii=False)})
            st.session_state.constructor_result = reply
        except WorkbenchError as exc:
            history.pop()
            st.error(str(exc))
        except Exception as exc:
            history.pop()
            st.error(f"Unexpected constructor error: {exc}")
        else:
            st.rerun()
