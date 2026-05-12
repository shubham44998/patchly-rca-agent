"""
ui/app.py — Patchly RCA Agent — Streamlit Frontend

Talks to the FastAPI backend at API_URL (default: http://localhost:8000).

Run:
  streamlit run ui/app.py
"""

import os
import json
import httpx
import streamlit as st

API_URL = os.getenv("API_URL", "http://localhost:8000")

st.set_page_config(
    page_title="Patchly RCA Agent",
    page_icon="🔍",
    layout="wide",
)

# ── Sidebar ───────────────────────────────────────────────────
with st.sidebar:
    st.title("🔍 Patchly RCA Agent")
    st.caption("AI-powered Root Cause Analysis")
    st.divider()

    page = st.radio("Navigate", ["Analyze Incident", "Saved Reports"], label_visibility="collapsed")

    st.divider()
    st.caption(f"API: `{API_URL}`")
    try:
        r = httpx.get(f"{API_URL}/health", timeout=2)
        st.success("API online ✓") if r.status_code == 200 else st.error("API error")
    except Exception:
        st.error("API offline ✗")


# ── Page: Analyze ─────────────────────────────────────────────
if page == "Analyze Incident":
    st.header("Analyze Incident")

    input_mode = st.segmented_control(
        "Input type",
        ["Text Alert", "Log File Path", "JSON Payload", "Upload Log File"],
        default="Text Alert",
    )

    incident_input = ""
    source         = None
    uploaded_file  = None

    if input_mode == "Text Alert":
        incident_input = st.text_area(
            "Alert / incident description",
            placeholder="CRITICAL: payment-service down. DB connection pool exhausted. 503s on /checkout",
            height=120,
        )
        source = "text_message"

    elif input_mode == "Log File Path":
        incident_input = st.text_input(
            "Absolute path to log file",
            placeholder="/var/log/app/error.log",
        )
        source = "log_file"

    elif input_mode == "JSON Payload":
        incident_input = st.text_area(
            "JSON payload (PagerDuty / webhook)",
            placeholder='{"text": "API 503", "service": "checkout", "error_rate": "98%"}',
            height=120,
        )
        source = None  # auto-detect

    elif input_mode == "Upload Log File":
        uploaded_file = st.file_uploader("Upload log file", type=["log", "txt", "out"])

    st.divider()
    run_btn = st.button("🚀 Run RCA Investigation", type="primary", use_container_width=True)

    if run_btn:
        # ── Validate ──────────────────────────────────────────
        if input_mode != "Upload Log File" and not incident_input.strip():
            st.warning("Please provide an input before running.")
            st.stop()
        if input_mode == "Upload Log File" and not uploaded_file:
            st.warning("Please upload a log file.")
            st.stop()

        # ── Call API ──────────────────────────────────────────
        with st.spinner("🔍 Investigating... this may take 30–120 seconds"):
            try:
                if input_mode == "Upload Log File":
                    resp = httpx.post(
                        f"{API_URL}/analyze/upload",
                        files={"file": (uploaded_file.name, uploaded_file.getvalue(), "text/plain")},
                        timeout=300,
                    )
                else:
                    resp = httpx.post(
                        f"{API_URL}/analyze",
                        json={"input": incident_input, "source": source},
                        timeout=300,
                    )

                if resp.status_code != 200:
                    st.error(f"API error {resp.status_code}: {resp.text}")
                    st.stop()

                data = resp.json()

            except httpx.ConnectError:
                st.error("Cannot connect to API. Is `uvicorn api.main:app` running?")
                st.stop()
            except Exception as e:
                st.error(f"Request failed: {e}")
                st.stop()

        # ── Display result ────────────────────────────────────
        st.success("Investigation complete!")

        col1, col2, col3 = st.columns(3)
        col1.metric("Steps Taken", data["steps_taken"])
        col2.metric("LLM Provider", data["provider"])
        col3.metric("Timestamp", data["timestamp"][:19].replace("T", " "))

        st.divider()
        st.subheader("📋 RCA Report")
        st.code(data["rca_report"], language=None)

        if data.get("report_saved"):
            st.caption(f"💾 Saved to: `{data['report_saved']}`")

        st.download_button(
            "⬇️ Download Report",
            data=data["rca_report"],
            file_name=f"rca_{data['timestamp'][:19].replace(':', '-').replace('T', '_')}.txt",
            mime="text/plain",
        )


# ── Page: Saved Reports ───────────────────────────────────────
elif page == "Saved Reports":
    st.header("Saved Reports")

    try:
        resp = httpx.get(f"{API_URL}/reports", timeout=10)
        reports = resp.json()
    except Exception as e:
        st.error(f"Failed to load reports: {e}")
        st.stop()

    if not reports:
        st.info("No saved reports yet. Run an investigation first.")
        st.stop()

    st.caption(f"{len(reports)} report(s) found")

    for r in reports:
        with st.expander(f"📄 {r['report_id']}  —  {r['created_at'][:19].replace('T', ' ')}  ({r['size_bytes']} bytes)"):
            col1, col2 = st.columns([4, 1])

            with col1:
                if st.button("Load Report", key=f"load_{r['report_id']}"):
                    try:
                        detail = httpx.get(f"{API_URL}/reports/{r['report_id']}", timeout=10).json()
                        st.code(detail["content"], language=None)
                        st.download_button(
                            "⬇️ Download",
                            data=detail["content"],
                            file_name=f"{r['report_id']}.txt",
                            mime="text/plain",
                            key=f"dl_{r['report_id']}",
                        )
                    except Exception as e:
                        st.error(f"Failed to load: {e}")

            with col2:
                if st.button("🗑️ Delete", key=f"del_{r['report_id']}", type="secondary"):
                    try:
                        httpx.delete(f"{API_URL}/reports/{r['report_id']}", timeout=10)
                        st.success("Deleted")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to delete: {e}")
