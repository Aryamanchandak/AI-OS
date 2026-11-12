"""Podcast Summariser — Streamlit UI.

Run with:  streamlit run app.py
"""
import os

import streamlit as st

from config import DEFAULT_MODEL, OUTPUT_SUMMARIES, OUTPUT_TRANSCRIPTS
from orchestrator import (
    IngestError,
    RSSError,
    SummariseError,
    TranscribeError,
    estimate_cost,
    get_latest_episode,
    load_podcasts,
    run as pipeline_run,
)

# =============================================================================
# Page setup
# =============================================================================

st.set_page_config(page_title="Podcast Summariser", page_icon="🎙️", layout="centered")

# API-key sanity check
missing = []
if not (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")) or \
        os.environ.get("GEMINI_API_KEY", "").startswith("your_"):
    missing.append("GEMINI_API_KEY")
if missing:
    st.error(f"Missing environment variables: {', '.join(missing)}. Set them in your .env file.")
    st.stop()

# Session state
if "active" not in st.session_state:
    st.session_state.active = None

# =============================================================================
# Sidebar — history
# =============================================================================

with st.sidebar:
    st.subheader("Previous summaries")
    summary_files = sorted(OUTPUT_SUMMARIES.glob("*.md"), reverse=True)
    if not summary_files:
        st.caption("No summaries yet. Run one below.")
    for f in summary_files[:10]:
        label = f.stem.replace("_", " ")[:48]
        if st.button(label, key=f"hist_{f.stem}", use_container_width=True):
            transcript_file = OUTPUT_TRANSCRIPTS / f.name.replace("_summary", "_transcript")
            st.session_state.active = {
                "summary": f.read_text(),
                "transcript": transcript_file.read_text() if transcript_file.exists() else "",
                "title": label,
                "from_history": True,
            }
            st.rerun()

# =============================================================================
# Main header
# =============================================================================

st.title("🎙️ Podcast Summariser")
st.caption("Pick a podcast, get the latest episode summarised. Transcripts and summaries are saved as Markdown.")

# =============================================================================
# Input panel
# =============================================================================

podcasts = load_podcasts()
if not podcasts:
    st.error("No podcasts found in `podcasts.yaml`. Add some RSS feeds and reload.")
    st.stop()

podcast_names = [p["name"] for p in podcasts]
selected_name = st.selectbox("Podcast", podcast_names)
selected = next(p for p in podcasts if p["name"] == selected_name)

col_a, col_b = st.columns(2)
with col_a:
    diarise = st.checkbox("Speaker diarisation", value=False)
with col_b:
    model = st.selectbox(
        "Summary model",
        ["gemini-2.5-pro", "gemini-2.5-flash"],
        index=0 if DEFAULT_MODEL == "gemini-2.5-pro" else 1,
    )

with st.expander("Upload audio instead of using RSS"):
    uploaded = st.file_uploader(
        "Upload audio file",
        type=["mp3", "wav", "m4a", "mp4", "ogg", "flac"],
    )

# Show latest episode preview before running
with st.expander("Preview latest episode from RSS", expanded=False):
    if st.button("Fetch episode info", key="preview"):
        with st.spinner("Checking RSS…"):
            try:
                ep = get_latest_episode(selected["rss"])
                st.write(f"**{ep['title']}**")
                if ep["published"]:
                    st.caption(ep["published"])
                if ep["duration_seconds"]:
                    mins = ep["duration_seconds"] / 60
                    est = estimate_cost(ep["duration_seconds"], diarise, model)
                    st.caption(
                        f"{mins:.0f} min · est. ${est['total_usd']:.2f} · ~{est['estimated_minutes']:.0f} min to process"
                    )
            except RSSError as e:
                st.error(str(e))

run_clicked = st.button("▶ Generate summary", type="primary", use_container_width=True)

# =============================================================================
# Pipeline run
# =============================================================================

if run_clicked:
    summary_buf: list[str] = []
    result: dict = {}

    with st.status("Processing…", expanded=True) as status:
        step_text = st.empty()
        summary_placeholder = st.empty()

        def on_chunk(chunk: str):
            summary_buf.append(chunk)
            summary_placeholder.markdown("".join(summary_buf))

        try:
            result = pipeline_run(
                podcast_name=selected_name,
                rss_url=selected["rss"],
                diarise=diarise,
                model=model,
                upload=uploaded if uploaded is not None else None,
                upload_name=uploaded.name if uploaded else "",
                progress_callback=lambda s, d: step_text.write(f"⏳ {d}"),
                on_chunk=on_chunk,
            )

            status.update(label="Done ✓", state="complete")

        except RSSError as e:
            status.update(label="RSS error", state="error")
            st.error(f"RSS fetch failed: {e}")
            st.stop()
        except IngestError as e:
            status.update(label="Download failed", state="error")
            st.error(f"Audio download failed: {e}")
            st.stop()
        except TranscribeError as e:
            status.update(label="Transcription failed", state="error")
            st.error(f"Transcription failed: {e}")
            st.stop()
        except SummariseError as e:
            status.update(label="Summarisation failed", state="error")
            st.error(f"Summarisation failed: {e}")
            st.stop()

    if result:
        st.session_state.active = {
            "summary": result["summary_text"],
            "transcript": result["transcript_text"],
            "title": result["episode_title"],
            "metadata": result["metadata"],
            "summary_path": result["summary_path"],
            "transcript_path": result["transcript_path"],
            "from_history": False,
        }
        st.rerun()

# =============================================================================
# Display active result
# =============================================================================
1
active = st.session_state.active
if active and active.get("summary"):
    st.divider()
    tab_summary, tab_transcript, tab_meta = st.tabs(
        ["📝 Summary", "📜 Transcript", "ℹ️ Metadata"]
    )

    with tab_summary:
        st.markdown(active["summary"])
        if active.get("summary_path"):
            st.caption(f"Saved to `{active['summary_path']}`")
        st.download_button(
            "⬇ Download summary (.md)",
            data=active["summary"],
            file_name=Path(active.get("summary_path", "summary.md")).name,
            mime="text/markdown",
        )

    with tab_transcript:
        st.text_area(
            "Transcript",
            active["transcript"],
            height=500,
            label_visibility="collapsed",
        )
        if active.get("transcript_path"):
            st.caption(f"Saved to `{active['transcript_path']}`")
        st.download_button(
            "⬇ Download transcript (.md)",
            data=active["transcript"],
            file_name=Path(active.get("transcript_path", "transcript.md")).name,
            mime="text/markdown",
        )

    with tab_meta:
        if active.get("from_history"):
            st.caption("Loaded from saved file.")
        else:
            m = active.get("metadata", {})
            st.write(f"**Episode:** {m.get('title', '—')}")
            st.write(f"**Podcast:** {m.get('podcast_name', '—')}")
            st.write(f"**Source:** {m.get('source_url', '—')}")
            st.write(f"**Duration:** {m.get('duration_seconds', 0) / 60:.1f} min")
            if m.get("speaker_count"):
                st.write(f"**Speakers identified:** {m['speaker_count']}")
            st.write(f"**Diarisation:** {'on' if m.get('diarised') else 'off'}")
            st.write(f"**Model:** `{m.get('model', DEFAULT_MODEL)}`")
            st.write(f"**Transcript cached:** {'yes' if m.get('transcript_cached') else 'no'}")
            st.write(f"**Run at:** {m.get('timestamp', '—')}")
