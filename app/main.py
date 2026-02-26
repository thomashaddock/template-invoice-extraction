import time

from dotenv import load_dotenv
load_dotenv()

import streamlit as st

from services import ExecutionsService
from utils import render_invoice_data

st.set_page_config(
    page_title="Doc2Data Demo",
    page_icon="📄",
    layout="centered",
)

if "processing" not in st.session_state:
    st.session_state.processing = False
if "result" not in st.session_state:
    st.session_state.result = None

st.html("""
<style>
    .stApp { background-color: #ffffff; }

    /* Hero banner */
    .hero {
        background: linear-gradient(135deg, #f7f8fa 0%, #eef1f5 100%);
        border-radius: 16px;
        text-align: center;
        padding: 3rem 2rem 2rem 2rem;
        margin-bottom: 1.5rem;
    }
    .hero h1 {
        font-size: 2rem;
        font-weight: 700;
        color: #1a1a1a;
        margin: 0 0 0.5rem 0;
    }
    .hero p {
        color: #555;
        font-size: 1rem;
        margin: 0;
    }

    /* Upload card */
    .upload-card {
        background: #fff;
        border: 1px solid #e5e7eb;
        border-radius: 12px;
        padding: 1.5rem;
        margin-bottom: 1.5rem;
    }

    /* File uploader drop zone */
    [data-testid="stFileUploader"] > div {
        border: 2px dashed #ccd0d5 !important;
        border-radius: 10px !important;
        background: #fafbfc !important;
        transition: all 0.2s ease;
    }
    [data-testid="stFileUploader"] > div:hover {
        border-color: #0062ff !important;
        background: #f0f5ff !important;
    }

    /* Run Crew button */
    .stButton > button {
        background-color: #0062ff !important;
        border-color: #0062ff !important;
        color: white !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
        font-size: 1rem !important;
        padding: 0.6rem 2rem !important;
    }
    .stButton > button:hover {
        background-color: #0050d4 !important;
        border-color: #0050d4 !important;
    }
    .stButton > button:disabled {
        background-color: #a0c4ff !important;
        border-color: #a0c4ff !important;
    }

    /* Steps row */
    .steps-row {
        display: flex;
        justify-content: center;
        gap: 3rem;
        padding: 1.5rem 0;
    }
    .step {
        text-align: center;
        max-width: 160px;
    }
    .step-number {
        display: inline-block;
        width: 32px;
        height: 32px;
        line-height: 32px;
        border-radius: 50%;
        background: #0062ff;
        color: white;
        font-weight: 700;
        font-size: 0.9rem;
        margin-bottom: 0.5rem;
    }
    .step h4 {
        margin: 0 0 0.25rem 0;
        font-size: 0.95rem;
        color: #1a1a1a;
    }
    .step p {
        margin: 0;
        font-size: 0.8rem;
        color: #888;
    }

    /* Result card */
    .result-header {
        font-size: 1.1rem;
        font-weight: 600;
        color: #1a1a1a;
        margin-bottom: 1rem;
    }

    /* Footer */
    .footer-center {
        display: flex;
        justify-content: center;
        text-align: center;
        color: #aaa;
        font-size: 0.8rem;
        padding: 1rem 0;
    }
</style>
""")


# ── Sidebar ─────────────────────────────────────────────────

with st.sidebar:
    st.logo("app/public/crewai.svg", size="large")
    st.divider()
    st.markdown(
        """
        **How it works**
        1. Upload a PDF invoice
        2. CrewAI extracts the data
        3. Record saved to database

        [Try CrewAI for free](https://app.crewai.com/)
        """
    )


# ── Hero ────────────────────────────────────────────────────

st.html("""
<div class="hero">
    <h1>Doc2Data Demo</h1>
    <p>Upload your PDF invoice and let CrewAI extract the data for you</p>
</div>
""")


# ── Upload + Run ────────────────────────────────────────────

uploaded_file = st.file_uploader(
    "Choose a PDF file",
    type="pdf",
    label_visibility="collapsed",
)

run_clicked = st.button(
    "Run Crew",
    use_container_width=True,
    disabled=(uploaded_file is None),
)

if run_clicked and uploaded_file is not None:
    st.session_state.processing = True
    st.session_state.result = None

    pdf_bytes = uploaded_file.getvalue()
    filename = uploaded_file.name

    progress = st.empty()
    status_text = st.empty()

    with progress.container():
        bar = st.progress(0, text="Uploading PDF to Google Drive...")

    try:
        service = ExecutionsService()

        bar.progress(20, text="Uploading PDF to Google Drive...")
        kickoff_id = service.start_execution(pdf_bytes, filename)

        bar.progress(40, text="Crew kicked off — waiting for results...")
        status_text.caption(f"Execution ID: `{kickoff_id}`")

        poll_count = 0
        max_polls = 60
        result = None
        while poll_count < max_polls:
            time.sleep(5)
            poll_count += 1
            pct = min(40 + int((poll_count / max_polls) * 55), 95)
            bar.progress(pct, text=f"Processing... (polling {poll_count})")

            try:
                response = service.crewai.status(kickoff_id)
                state = response.get("state", "")
                if state == "SUCCESS":
                    import json
                    raw = response.get("result")
                    if isinstance(raw, str):
                        result = json.loads(raw)
                    else:
                        result = raw
                    break
                elif state in ("FAILURE", "REVOKED"):
                    result = {"extraction_status": "failed", "error_message": f"Execution {state.lower()}"}
                    break
            except Exception:
                continue

        bar.progress(100, text="Done!")
        time.sleep(0.5)
        progress.empty()
        status_text.empty()

        if result:
            st.session_state.result = result
        else:
            st.session_state.result = {
                "extraction_status": "pending",
                "error_message": "Timed out waiting for results. Check back later.",
            }

    except Exception as e:
        progress.empty()
        status_text.empty()
        st.session_state.result = {
            "extraction_status": "failed",
            "error_message": str(e),
        }

    st.session_state.processing = False


# ── Results ─────────────────────────────────────────────────

if st.session_state.result:
    st.divider()
    result = st.session_state.result
    status = result.get("extraction_status", "unknown")

    if status in ("processed", "completed"):
        st.success("Invoice processed successfully!")
        db_id = result.get("db_record_id")
        if db_id:
            st.markdown(f"**Database Record ID:** `{db_id}`")
        invoice_data = result.get("invoice_data", {})
        if invoice_data:
            render_invoice_data(invoice_data)
        else:
            st.info("No structured data returned.")

    elif status == "failed":
        st.error(f"Extraction failed: {result.get('error_message', 'Unknown error')}")

    elif status == "skipped":
        st.warning(f"Skipped: {result.get('error_message', 'Document was not a valid invoice')}")

    elif status == "pending":
        st.info(result.get("error_message", "Still processing..."))


# ── Steps ───────────────────────────────────────────────────

if not st.session_state.result:
    st.html("""
    <div class="steps-row">
        <div class="step">
            <div class="step-number">1</div>
            <h4>Upload</h4>
            <p>Drop your PDF invoice</p>
        </div>
        <div class="step">
            <div class="step-number">2</div>
            <h4>Process</h4>
            <p>CrewAI extracts the data</p>
        </div>
        <div class="step">
            <div class="step-number">3</div>
            <h4>Results</h4>
            <p>View extracted data &amp; DB record</p>
        </div>
    </div>
    """)


# ── Footer ──────────────────────────────────────────────────

with st._bottom:
    st.html("""
    <p class="footer-center">
        CrewAI &copy; Copyright 2025, All Rights Reserved by CrewAI&trade;, Inc.
    </p>
    """)
