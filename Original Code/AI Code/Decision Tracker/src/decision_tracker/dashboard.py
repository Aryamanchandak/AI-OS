from __future__ import annotations
import os
import streamlit as st
import pandas as pd
import plotly.express as px
from decision_tracker.analytics import report
from decision_tracker.service import DecisionTracker
from decision_tracker.recall import recall

st.set_page_config(page_title="Decision Ledger",page_icon="◈",layout="wide",initial_sidebar_state="expanded")
st.markdown("""<style>@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;600&family=Instrument+Serif&display=swap');:root{--ink:#171814;--paper:#f3efe5;--amber:#b65c22;--sage:#526b54}.stApp{background:var(--paper);color:var(--ink);font-family:'DM Sans',sans-serif}h1,h2,h3{font-family:'Instrument Serif',serif!important;letter-spacing:-.025em}[data-testid=stSidebar]{background:#e8e1d2;border-right:1px solid #cfc4b1}[data-testid=metric-container]{background:#fffaf0;border:1px solid #d8cdbb;border-radius:2px;padding:1rem}div[data-testid=stDataFrame]{border:1px solid #d8cdbb}button{transition:transform .18s ease}button:hover{transform:translateY(-1px)}#MainMenu,footer{visibility:hidden}</style>""",unsafe_allow_html=True)
if "view" not in st.session_state:st.session_state.view="Overview"
@st.cache_data(ttl=30)
def load(path:str):
    t=DecisionTracker(path);ds=t.store.list();return ds,report(ds),t.store.verify()
def main():
    path=os.getenv("DT_DB_PATH",".decision-tracker/decision_tracker.db")
    try:ds,summary,integrity=load(path)
    except Exception as e:st.error(f"Could not read the local ledger: {e}");return
    with st.sidebar:
        st.markdown("## Ledger view"); statuses=st.multiselect("Status",sorted({d.status.value for d in ds}));classes=st.multiselect("Class",sorted({d.decision_class.value for d in ds}));st.caption("Read-only · local data")
    st.title("Decision Ledger");st.caption("Calibration before confidence. Evidence before hindsight.")
    cols=st.columns(4);cols[0].metric("Records",summary["total"]);cols[1].metric("Live",summary["live"]);cols[2].metric("Resolved",summary["resolved"]);cols[3].metric("Mean Brier",f'{summary["mean_brier"]:.3f}' if summary["mean_brier"] is not None else "—")
    filtered=[d for d in ds if (not statuses or d.status.value in statuses) and (not classes or d.decision_class.value in classes)]
    tab1,tab2,tab3,tab4=st.tabs(["Open decisions","Calibration","Recall","Integrity"])
    with tab1:
        rows=[{"ID":d.id,"Title":d.title,"Class":d.decision_class.value,"Status":d.status.value,"Probability":d.claim.probability,"Resolution date":d.claim.resolution_date} for d in filtered]
        if rows:st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)
        else:st.info("No decisions match these filters. Capture one with `dt log`.")
    with tab2:
        cal=summary["calibration"]
        if cal:
            frame=pd.DataFrame(cal);fig=px.scatter(frame,x="declared",y="realised",size="n",hover_name="bucket",color_discrete_sequence=["#b65c22"]);fig.add_shape(type="line",x0=0,y0=0,x1=1,y1=1,line=dict(color="#526b54",dash="dash"));fig.update_layout(paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",font_family="DM Sans");st.plotly_chart(fig,use_container_width=True)
        else:st.info("Calibration appears after at least 20 resolved, non-backfilled forecasts in a confidence bucket.")
    with tab3:
        query=st.text_input("Find analogous decisions")
        if query:
            matches=recall(query,ds,5)
            if matches:st.dataframe(pd.DataFrame(matches),use_container_width=True,hide_index=True)
            else:st.info("No similar decisions found yet.")
    with tab4:
        if integrity[0]:st.success(integrity[1])
        else:st.error(integrity[1])
if __name__=="__main__":main()
