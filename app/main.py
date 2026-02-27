import base64
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

import streamlit as st

from services import ExecutionsService
from utils import render_invoice_data
# from webhook_server import ensure_webhook_server_running

SAMPLES_DIR = Path(__file__).parent / "public" / "samples"
SAMPLE_INVOICES = [
    {"name": "Anthony Johnson", "invoice_id": "35339", "file": "invoice_Anthony Johnson_35339.pdf"},
    {"name": "Barry Gonzalez", "invoice_id": "2765", "file": "invoice_Barry Gonzalez_2765.pdf"},
    {"name": "Bill Eplett", "invoice_id": "27119", "file": "invoice_Bill Eplett_27119.pdf"},
]

st.set_page_config(
    page_title="Doc2Data Demo",
    page_icon="📄",
    layout="centered",
)

# ensure_webhook_server_running()

if "processing" not in st.session_state:
    st.session_state.processing = False
if "result" not in st.session_state:
    st.session_state.result = None
if "selected_sample" not in st.session_state:
    st.session_state.selected_sample = None

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

    /* All buttons — shared base */
    .stButton > button {
        border-radius: 8px !important;
        font-weight: 600 !important;
        font-size: 0.9rem !important;
        padding: 0.5rem 1.5rem !important;
    }

    /* Primary buttons (Run Crew, selected sample) */
    [data-testid="stBaseButton-primary"] {
        background-color: #0062ff !important;
        border-color: #0062ff !important;
        color: white !important;
    }
    [data-testid="stBaseButton-primary"]:hover {
        background-color: #0050d4 !important;
        border-color: #0050d4 !important;
    }
    [data-testid="stBaseButton-primary"]:disabled {
        background-color: #a0c4ff !important;
        border-color: #a0c4ff !important;
    }

    /* Secondary buttons (sample selection) */
    [data-testid="stBaseButton-secondary"] {
        background-color: transparent !important;
        border: 1px solid #ccd0d5 !important;
        color: #555 !important;
        font-size: 0.85rem !important;
    }
    [data-testid="stBaseButton-secondary"]:hover {
        border-color: #0062ff !important;
        color: #0062ff !important;
        background-color: #f0f5ff !important;
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

    /* Sample invoice cards */
    .sample-divider {
        display: flex;
        align-items: center;
        gap: 1rem;
        margin: 1.25rem 0 1rem 0;
        color: #aaa;
        font-size: 0.85rem;
    }
    .sample-divider::before, .sample-divider::after {
        content: "";
        flex: 1;
        height: 1px;
        background: #e5e7eb;
    }
    .sample-card {
        border: 2px solid #e5e7eb;
        border-radius: 10px;
        padding: 1rem 0.75rem;
        text-align: center;
        transition: all 0.2s ease;
        cursor: default;
        background: #fafbfc;
    }
    .sample-card.active {
        border-color: #0062ff;
        background: #f0f5ff;
        box-shadow: 0 0 0 3px rgba(0, 98, 255, 0.12);
    }
    .sample-card .icon {
        font-size: 1.6rem;
        margin-bottom: 0.35rem;
    }
    .sample-card .name {
        font-weight: 600;
        font-size: 0.9rem;
        color: #1a1a1a;
        margin-bottom: 0.15rem;
    }
    .sample-card .inv-id {
        font-size: 0.75rem;
        color: #888;
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
        3. View structured results

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

if uploaded_file is not None:
    st.session_state.selected_sample = None

# ── Sample invoices ─────────────────────────────────────────

st.html('<div class="sample-divider">or try a sample invoice</div>')

sample_cols = st.columns(3)
for i, sample in enumerate(SAMPLE_INVOICES):
    with sample_cols[i]:
        is_active = (
            st.session_state.selected_sample is not None
            and st.session_state.selected_sample["file"] == sample["file"]
        )
        active_cls = "active" if is_active else ""
        st.html(f"""
        <div class="sample-card {active_cls}">
            <div class="icon">📄</div>
            <div class="name">{sample["name"]}</div>
            <div class="inv-id">Invoice #{sample["invoice_id"]}</div>
        </div>
        """)
        if st.button(
            "✓ Selected" if is_active else "Use this sample",
            key=f"sample_{i}",
            use_container_width=True,
            type="primary" if is_active else "secondary",
        ):
            if is_active:
                st.session_state.selected_sample = None
            else:
                st.session_state.selected_sample = sample
            st.session_state.result = None
            st.rerun()

# ── Sample preview ──────────────────────────────────────────

if st.session_state.selected_sample is not None:
    sample_path = SAMPLES_DIR / st.session_state.selected_sample["file"]
    sample_bytes = sample_path.read_bytes()
    b64 = base64.b64encode(sample_bytes).decode()
    with st.expander("Preview selected invoice", expanded=True):
        st.html(
            f'<iframe src="data:application/pdf;base64,{b64}" '
            f'width="100%" height="450" style="border:none;border-radius:8px;"></iframe>'
        )

has_input = uploaded_file is not None or st.session_state.selected_sample is not None

run_clicked = st.button(
    "Run Crew",
    type="primary",
    use_container_width=True,
    disabled=(not has_input),
)

if run_clicked and has_input:
    st.session_state.processing = True
    st.session_state.result = None

    if uploaded_file is not None:
        pdf_bytes = uploaded_file.getvalue()
        filename = uploaded_file.name
    else:
        sample_path = SAMPLES_DIR / st.session_state.selected_sample["file"]
        pdf_bytes = sample_path.read_bytes()
        filename = st.session_state.selected_sample["file"]

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
        result = service.wait_for_result(
            kickoff_id,
            timeout=300,
            progress_cb=lambda pct, msg: bar.progress(pct, text=msg),
        )

        bar.progress(100, text="Complete!")
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
        msg = str(e)
        # Hint when API returns non-JSON (wrong URL, 401, 404, 500)
        if "Expecting value" in msg or "JSON" in msg or "401" in msg or "403" in msg:
            msg = f"{msg} — Check Heroku config: CREWAI_ENTERPRISE_API_URL and CREWAI_ENTERPRISE_BEARER_TOKEN."
        st.session_state.result = {
            "extraction_status": "failed",
            "error_message": msg,
        }

    st.session_state.processing = False


# ── Results ─────────────────────────────────────────────────

if st.session_state.result:
    st.divider()
    result = st.session_state.result
    status = result.get("extraction_status", "unknown")

    if status in ("processed", "completed"):
        st.success("Invoice processed successfully!")
        invoice_data = result.get("invoice_data", {})
        if invoice_data:
            render_invoice_data(invoice_data)
            with st.expander("Raw JSON", expanded=False):
                st.json(invoice_data)
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
            <p>View extracted invoice data</p>
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
