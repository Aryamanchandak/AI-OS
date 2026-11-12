from __future__ import annotations

import html
import os

import streamlit as st

from steelman.forensics import assess_forensic_flag, load_flag_definitions
from steelman.deliberation import FullSteelmanPipeline
from steelman.domains import DomainPack
from steelman.models import Source, SourceStance, SourceTier, TrackerEntry, VerificationGrade
from steelman.pipeline import SteelmanPipeline
from steelman.providers import get_provider
from steelman.storage import SQLiteStore


st.set_page_config(
    page_title="Steelman / Evidence before eloquence",
    page_icon="◒",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600&family=Fraunces:opsz,wght@9..144,600;9..144,700&display=swap');
:root {
  --ink: #182525; --muted: #66706c; --paper: #f4efe5; --paper-2: #eae1d3;
  --line: #cfc2af; --rust: #b44c2b; --moss: #34594d; --gold: #c8943b;
}
.stApp { background: var(--paper); color: var(--ink); font-family: 'DM Sans', sans-serif; }
[data-testid="stSidebar"] { background: #182525; border-right: 1px solid #30403e; }
[data-testid="stSidebar"] * { color: #f4efe5; }
[data-testid="stSidebar"] [data-baseweb="select"] * { color: var(--ink); }
h1, h2, h3 { font-family: 'Fraunces', serif !important; letter-spacing: -0.035em; color: var(--ink); }
h1 { font-size: clamp(2.8rem, 6vw, 5.3rem) !important; line-height: .95 !important; max-width: 900px; }
.eyebrow { color: var(--rust); font-size: .76rem; font-weight: 600; letter-spacing: .13em; text-transform: uppercase; }
.hero-copy { color: var(--muted); font-size: 1.08rem; line-height: 1.65; max-width: 760px; margin-bottom: 2.2rem; }
.status-strip { border-left: 4px solid var(--rust); background: rgba(255,255,255,.35); padding: 1rem 1.2rem; margin: 1rem 0 1.5rem; }
.status-strip strong { color: var(--ink); }
[data-testid="metric-container"] { background: rgba(255,255,255,.38); border: 1px solid var(--line); border-radius: 4px; padding: 1rem; }
.stButton > button, .stDownloadButton > button { border-radius: 3px; border: 1px solid var(--ink); transition: all .16s ease; }
.stButton > button:hover, .stDownloadButton > button:hover { background: var(--ink); color: var(--paper); transform: translateY(-1px); }
div[data-baseweb="input"]:focus-within, div[data-baseweb="textarea"]:focus-within { box-shadow: 0 0 0 2px var(--gold); }
.block-container { max-width: 1240px; padding-top: 3rem; padding-bottom: 6rem; }
hr { border-color: var(--line); }
@keyframes reveal { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
.element-container { animation: reveal .32s ease-out both; }
@media (max-width: 700px) { .block-container { padding: 1.4rem 1rem 4rem; } h1 { font-size: 2.65rem !important; } }
.mobile-cards { display: flex; gap: 12px; overflow-x: auto; scroll-snap-type: x mandatory; padding: 8px 0 20px; }
.mobile-card { min-width: min(82vw, 340px); scroll-snap-align: start; background: #fffaf1; border: 1px solid var(--line); border-top: 4px solid var(--rust); padding: 18px; }
</style>
""",
    unsafe_allow_html=True,
)

for key, value in {"latest_run": None, "active_view": "Build a steelman"}.items():
    if key not in st.session_state:
        st.session_state[key] = value


@st.cache_resource
def get_store(path: str) -> SQLiteStore:
    return SQLiteStore(path)


@st.cache_data
def get_forensic_flags(path: str | None):
    return load_flag_definitions(path)


def render_header(kicker: str, title: str, copy: str) -> None:
    st.markdown(f'<div class="eyebrow">{html.escape(kicker)}</div>', unsafe_allow_html=True)
    st.title(title)
    st.markdown(f'<div class="hero-copy">{html.escape(copy)}</div>', unsafe_allow_html=True)


def build_sources(count: int) -> list[Source]:
    sources = []
    for index in range(count):
        title = st.session_state.get(f"source_title_{index}", "").strip()
        excerpt = st.session_state.get(f"source_excerpt_{index}", "").strip()
        if not title and not excerpt:
            continue
        if not title or not excerpt:
            raise ValueError(f"Source {index + 1} needs both a title and an excerpt")
        sources.append(
            Source(
                title=title,
                publisher=st.session_state.get(f"source_publisher_{index}", ""),
                author_or_advocate=st.session_state.get(f"source_advocate_{index}", ""),
                url=st.session_state.get(f"source_url_{index}", ""),
                excerpt=excerpt,
                tier=SourceTier(st.session_state.get(f"source_tier_{index}", "secondary")),
                stance=SourceStance(st.session_state.get(f"source_stance_{index}", "supports")),
            )
        )
    return sources


def render_run(run) -> None:
    st.markdown(
        f'<div class="status-strip"><strong>{html.escape(run.proponent_status.value)}</strong>'
        f" · Built with {html.escape(run.provider)} · {len(run.graph.warnings)} verification warning(s)</div>",
        unsafe_allow_html=True,
    )
    m1, m2, m3 = st.columns(3)
    m1.metric("Premise nodes", len(run.graph.nodes))
    m2.metric("Load-bearing", sum(node.load_bearing for node in run.graph.nodes))
    m3.metric("Sources supplied", len(run.sources))
    tabs = st.tabs(["Steelman", "Claim card", "Premise graph", "Verification", "Raw JSON"])
    with tabs[0]:
        st.markdown(run.rendered_steelman)
    with tabs[1]:
        st.json(run.claim_card.model_dump(mode="json"), expanded=True)
    with tabs[2]:
        for node in run.graph.nodes:
            label = f"{node.type.value} · {'load-bearing' if node.load_bearing else 'supporting'} · {node.strength}"
            with st.expander(label):
                st.write(node.text)
                dependencies = [edge.source_id for edge in run.graph.edges if edge.target_id == node.id]
                if dependencies:
                    st.caption(f"Depends on: {', '.join(dependencies)}")
        st.caption("The JSON export preserves exact node and edge IDs for graph tooling.")
    with tabs[3]:
        empirical = [result for result in run.graph.verifications if result.grade != VerificationGrade.NOT_APPLICABLE]
        if not empirical:
            st.info("No empirical premises were produced for verification.")
        for result in empirical:
            st.markdown(f"**{result.grade.value.upper()}** — `{result.node_id}`")
            st.write(result.note)
    with tabs[4]:
        payload = run.model_dump_json(indent=2)
        st.download_button("Download analysis JSON", payload, f"{run.claim_card.claim_hash}.json", "application/json")
        st.code(payload, language="json")


def render_analysis(store: SQLiteStore, provider_name: str, model: str) -> None:
    render_header(
        "World-model reconstruction",
        "Build the case that has to be true.",
        "Separate the claim, expose its load-bearing premises, and make every empirical dependency answer to evidence.",
    )
    with st.form("claim_form"):
        claim = st.text_area(
            "Claim",
            placeholder="Example: Extending supplier payment terms will improve free cash flow over the next two quarters.",
            height=110,
        )
        left, right = st.columns(2)
        scope = left.text_input("Scope", placeholder="Company, market, population, or jurisdiction")
        horizon = right.text_input("Time horizon", placeholder="e.g. next two quarters")
        source_count = st.number_input("Evidence sources to supply", 0, 5, 0)
        for index in range(int(source_count)):
            with st.expander(f"Source {index + 1}", expanded=index == 0):
                a, b = st.columns([2, 1])
                a.text_input("Title", key=f"source_title_{index}")
                b.text_input("Publisher", key=f"source_publisher_{index}")
                a, b = st.columns([2, 1])
                a.text_input("Named advocate / author", key=f"source_advocate_{index}")
                b.selectbox("Tier", ["primary", "secondary"], key=f"source_tier_{index}")
                st.text_input("URL (optional)", key=f"source_url_{index}")
                st.text_area("Relevant excerpt", key=f"source_excerpt_{index}")
                st.selectbox("Stance", ["supports", "contests", "neutral"], key=f"source_stance_{index}")
        submitted = st.form_submit_button("Reconstruct the strongest case", type="primary")
    if submitted:
        try:
            sources = build_sources(int(source_count))
            provider = get_provider(provider_name, model)
            with st.spinner("Excavating premises and checking evidence…"):
                run = SteelmanPipeline(provider).run(claim, scope or "unspecified", horizon or "unspecified", sources)
                store.save_analysis(run)
                st.session_state.latest_run = run
            st.success("Analysis saved.")
        except Exception as exc:
            st.error(f"Analysis could not be completed: {exc}")
    if st.session_state.latest_run is not None:
        render_run(st.session_state.latest_run)


def render_forensics(store: SQLiteStore) -> None:
    render_header(
        "Forensic accounting / v0 pack",
        "No escalation without a benign case.",
        "The SA01–SA15 catalog is intentionally generic and configurable. It is a review scaffold, not an authoritative accounting standard.",
    )
    try:
        flags = get_forensic_flags(os.getenv("STEELMAN_FORENSIC_FLAGS"))
    except Exception as exc:
        st.error(f"The forensic flag catalog could not be loaded: {exc}")
        return
    flag_map = {f"{flag.code} · {flag.name}": flag for flag in flags}
    with st.form("forensic_form"):
        company = st.text_input("Company or issuer")
        selected = st.selectbox("Flag", list(flag_map))
        flag = flag_map[selected]
        st.info(flag.prompt)
        observation = st.text_area("Observed signal", height=90)
        benign = st.text_area("Strongest benign management explanation", height=110)
        supporting = st.text_area(
            "Management-supporting evidence",
            placeholder="Paste the evidence, or explicitly write that none was found.",
        )
        contradictory = st.text_area("Contradictory evidence (optional)")
        residual = st.text_area("Residual risk after considering the benign case")
        grade = st.selectbox(
            "Evidence grade for the benign explanation",
            [grade.value for grade in VerificationGrade if grade != VerificationGrade.FABRICATED],
        )
        escalate = st.checkbox("Request escalation after steelmanning")
        submitted = st.form_submit_button("Run escalation gate", type="primary")
    if submitted:
        try:
            assessment = assess_forensic_flag(
                company=company,
                flag_code=flag.code,
                observation=observation,
                benign_explanation=benign,
                management_evidence=supporting,
                contradictory_evidence=contradictory,
                residual_risk=residual,
                verification_grade=VerificationGrade(grade),
                escalate_requested=escalate,
                flag_definitions=flags,
            )
            store.save_forensic_assessment(assessment)
            if assessment.escalation_allowed:
                st.success("Escalation allowed. The benign case and remaining risk are both recorded.")
            elif escalate:
                st.error("Escalation blocked until every steelman gate is satisfied.")
            else:
                st.info("Assessment saved without escalation.")
            for reason in assessment.gate_reasons:
                st.warning(reason)
            st.json(assessment.model_dump(mode="json"))
        except Exception as exc:
            st.error(f"Assessment could not be saved: {exc}")


def render_full_deliberation(store: SQLiteStore, provider_name: str, model: str) -> None:
    render_header("Budget-parity dual analysis", "Pressure-test both worlds.", "Six frames per side, cross-role hardening, blinded ordering, cruxes, predictions, and a rubric gate run as one auditable DAG.")
    with st.form("dual_form"):
        claim = st.text_area("Claim to test", height=100)
        a, b, c = st.columns(3)
        scope = a.text_input("Scope", key="dual_scope")
        horizon = b.text_input("Time horizon", key="dual_horizon")
        domain = c.selectbox("Domain pack", [item.value for item in DomainPack])
        rounds = st.slider("Red/Blue rounds", 1, 5, 3)
        submitted = st.form_submit_button("Run both sides under equal budget", type="primary")
    if submitted:
        try:
            provider = get_provider(provider_name, model)
            with st.spinner("Running parallel frames, hardening both sides, and extracting cruxes…"):
                analysis = FullSteelmanPipeline(provider, rounds=rounds, verification_cache=store).run(
                    claim, scope or "unspecified", horizon or "unspecified", domain=DomainPack(domain)
                )
                store.save_dual_analysis(analysis)
                for side in (analysis.claim, analysis.negation):
                    for prediction in side.predictions:
                        store.register_prediction(TrackerEntry(prediction=prediction))
            st.session_state.latest_dual = analysis
            st.success("Dual analysis saved and predictions preregistered.")
        except Exception as exc:
            st.error(f"Dual analysis could not be completed: {exc}")
    analysis = st.session_state.get("latest_dual")
    if not analysis:
        return
    m1, m2, m3 = st.columns(3)
    m1.metric("Rubric", f"{analysis.rubric.score}/{len(analysis.rubric.checks)}")
    m2.metric("Cruxes", len(analysis.cruxes))
    m3.metric("Budget parity", "enforced")
    st.caption("Blinded judge order: " + " → ".join(side.value for side in analysis.blinded_order))
    claim_tab, negation_tab, crux_tab, dag_tab = st.tabs(["Claim world", "Negation world", "Cruxes & cards", "DAG & raw state"])
    for tab, side in ((claim_tab, analysis.claim), (negation_tab, analysis.negation)):
        with tab:
            st.markdown(side.run.rendered_steelman)
            st.subheader("Parallel frames")
            for mode, text in side.frames.items():
                with st.expander(mode.value): st.write(text)
            st.subheader("Red / Blue hardening")
            for item in side.hardening:
                st.write(f"**Round {item.round_number}** — {item.attack}")
                st.write(item.repair)
            if side.retreat_path:
                st.subheader("Retreat path")
                for index, retreat in enumerate(side.retreat_path, 1): st.write(f"{index}. {retreat}")
    with crux_tab:
        cards = []
        for crux in analysis.cruxes:
            cards.append(f"<div class='mobile-card'><div class='eyebrow'>Crux</div><b>{html.escape(crux.disputed_proposition)}</b><p>{html.escape(crux.settling_observation)}</p></div>")
        for prediction in analysis.claim.predictions + analysis.negation.predictions:
            cards.append(f"<div class='mobile-card'><div class='eyebrow'>Prediction · {prediction.side.value}</div><b>{html.escape(prediction.proposition)}</b><p>Threshold: {prediction.threshold} {html.escape(prediction.unit)}</p></div>")
        st.markdown("<div class='mobile-cards'>" + "".join(cards) + "</div>", unsafe_allow_html=True)
    with dag_tab:
        st.write(" → ".join(analysis.dag_log))
        st.json(analysis.model_dump(mode="json"), expanded=False)


def render_tracker(store: SQLiteStore) -> None:
    render_header("Decision tracker", "Predictions have receipts.", "Resolve preregistered thresholds and watch calibration accumulate locally over time.")
    summary = store.calibration()
    a, b, c = st.columns(3)
    a.metric("Resolved", summary.resolved_count)
    b.metric("Brier score", "—" if summary.brier_score is None else summary.brier_score)
    c.metric("Accuracy", "—" if summary.accuracy is None else f"{summary.accuracy:.0%}")
    entries = store.list_tracker_entries()
    if not entries:
        st.info("Run a full deliberation to preregister predictions.")
        return
    for entry in entries:
        with st.expander(f"{entry.prediction.deadline} · {entry.prediction.side.value} · {entry.prediction.proposition}"):
            if entry.resolved:
                st.write(f"Observed: {entry.observed_value} · Outcome: {'met' if entry.outcome else 'missed'} · Confidence: {entry.confidence:.0%}")
            else:
                value = st.number_input("Observed change", key=f"observed_{entry.prediction.id}")
                if st.button("Resolve", key=f"resolve_{entry.prediction.id}"):
                    store.resolve_prediction(entry.prediction.id, value)
                    st.success("Prediction resolved. Reload this view to refresh calibration.")


def render_history(store: SQLiteStore) -> None:
    render_header("Local record", "Revisit what moved.", "Runs are stored in SQLite and retain graph-shaped nodes, edges, sources, and verification results.")
    rows = store.list_analyses()
    if not rows:
        st.info("No analyses have been saved yet.")
    for row in rows:
        with st.expander(f"{row['canonical_claim']} · {row['created_at'][:10]}"):
            st.caption(f"{row['provider']} · {row['id']}")
            if st.button("Open analysis", key=f"open_{row['id']}"):
                st.session_state.latest_run = store.get_analysis(row["id"])
                render_run(st.session_state.latest_run)
    assessments = store.list_forensic_assessments()
    st.subheader("Forensic assessments")
    if not assessments:
        st.info("No forensic assessments have been saved yet.")
    for assessment in assessments:
        state = "allowed" if assessment.escalation_allowed else "not escalated"
        st.write(f"**{assessment.flag_code} · {assessment.company or 'Unnamed issuer'}** — {state}")


def main() -> None:
    database_path = os.getenv("STEELMAN_DB", "steelman.db")
    store = get_store(database_path)
    with st.sidebar:
        st.markdown("## STEELMAN / 00")
        st.caption("Evidence before eloquence")
        view = st.radio("Workspace", ["Full deliberation", "Build a steelman", "Forensic review", "Decision tracker", "Saved work"])
        st.divider()
        provider_name = st.selectbox("Construction mode", ["deterministic", "openai"])
        model = st.text_input("OpenAI model", value="gpt-4.1-mini", disabled=provider_name != "openai")
        if provider_name == "openai" and not os.getenv("OPENAI_API_KEY"):
            st.warning("Set OPENAI_API_KEY before running OpenAI mode.")
        st.caption(f"Database: {database_path}")
    if view == "Full deliberation":
        render_full_deliberation(store, provider_name, model)
    elif view == "Build a steelman":
        render_analysis(store, provider_name, model)
    elif view == "Forensic review":
        render_forensics(store)
    elif view == "Decision tracker":
        render_tracker(store)
    else:
        render_history(store)


if __name__ == "__main__":
    main()
