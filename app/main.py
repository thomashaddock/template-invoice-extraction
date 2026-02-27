"""
Streamlit demo for doc2data: upload or select a sample PDF, run the CrewAI flow, display extracted invoice data.
"""
import io
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

import streamlit as st

try:
    import fitz  # pymupdf
except ImportError:
    fitz = None

from services import ExecutionsService
from utils import render_invoice_data

SAMPLES_DIR = Path(__file__).parent / "public" / "samples"
SAMPLE_INVOICES = [
    {"name": "Anthony Johnson", "invoice_id": "35339", "file": "invoice_Anthony Johnson_35339.pdf"},
    {"name": "Barry Gonzalez", "invoice_id": "2765", "file": "invoice_Barry Gonzalez_2765.pdf"},
    {"name": "Bill Eplett", "invoice_id": "27119", "file": "invoice_Bill Eplett_27119.pdf"},
]

st.set_page_config(
    page_title="Invoice Extraction Demo",
    page_icon="📄",
    layout="centered",
)

if "processing" not in st.session_state:
    st.session_state.processing = False
if "result" not in st.session_state:
    st.session_state.result = None
if "selected_sample" not in st.session_state:
    st.session_state.selected_sample = None
if "last_pdf_bytes" not in st.session_state:
    st.session_state.last_pdf_bytes = None
if "last_pdf_filename" not in st.session_state:
    st.session_state.last_pdf_filename = None

# CrewAI orange accent (brand)
ACCENT_ORANGE = "#F15A24"

st.html(f"""
<style>
    .stApp {{ background-color: #ffffff; }}

    /* Sidebar: light grey */
    [data-testid="stSidebar"] {{
        background: linear-gradient(180deg, #f5f5f5 0%, #eef1f5 100%);
    }}

    /* Hero banner */
    .hero {{
        background: linear-gradient(135deg, #f7f8fa 0%, #eef1f5 100%);
        border-radius: 16px;
        text-align: center;
        padding: 2rem 1.5rem;
        margin-bottom: 1.5rem;
    }}
    .hero h1 {{
        font-size: 1.75rem;
        font-weight: 700;
        color: #1a1a1a;
        margin: 0 0 0.5rem 0;
    }}
    .hero p {{
        color: #555;
        font-size: 0.95rem;
        margin: 0;
    }}

    /* File uploader drop zone */
    [data-testid="stFileUploader"] > div {{
        border: 2px dashed #ccd0d5 !important;
        border-radius: 10px !important;
        background: #fafbfc !important;
        transition: all 0.2s ease;
    }}
    [data-testid="stFileUploader"] > div:hover {{
        border-color: {ACCENT_ORANGE} !important;
        background: #fff8f5 !important;
    }}

    /* All buttons — shared base */
    .stButton > button {{
        border-radius: 8px !important;
        font-weight: 600 !important;
        font-size: 0.9rem !important;
        padding: 0.5rem 1.5rem !important;
    }}

    /* Primary buttons (Run Crew, selected sample) — CrewAI orange */
    [data-testid="stBaseButton-primary"] {{
        background-color: {ACCENT_ORANGE} !important;
        border-color: {ACCENT_ORANGE} !important;
        color: white !important;
    }}
    [data-testid="stBaseButton-primary"]:hover {{
        background-color: #d94e1a !important;
        border-color: #d94e1a !important;
    }}
    [data-testid="stBaseButton-primary"]:disabled {{
        background-color: #f5b099 !important;
        border-color: #f5b099 !important;
    }}

    /* Secondary buttons (sample selection) */
    [data-testid="stBaseButton-secondary"] {{
        background-color: transparent !important;
        border: 1px solid #ccd0d5 !important;
        color: #555 !important;
        font-size: 0.85rem !important;
    }}
    [data-testid="stBaseButton-secondary"]:hover {{
        border-color: {ACCENT_ORANGE} !important;
        color: {ACCENT_ORANGE} !important;
        background-color: #fff8f5 !important;
    }}

    /* Steps row */
    .steps-row {{
        display: flex;
        justify-content: center;
        gap: 3rem;
        padding: 1.5rem 0;
    }}
    .step {{
        text-align: center;
        max-width: 160px;
    }}
    .step-number {{
        display: inline-block;
        width: 32px;
        height: 32px;
        line-height: 32px;
        border-radius: 50%;
        background: {ACCENT_ORANGE};
        color: white;
        font-weight: 700;
        font-size: 0.9rem;
        margin-bottom: 0.5rem;
    }}
    .step h4 {{
        margin: 0 0 0.25rem 0;
        font-size: 0.95rem;
        color: #1a1a1a;
    }}
    .step p {{
        margin: 0;
        font-size: 0.8rem;
        color: #888;
    }}

    /* Extraction result box (bordered container) */
    .extraction-result-box,
    div[data-testid="stVerticalBlockBorderWrapper"] {{
        border: 1px solid #e5e7eb !important;
        border-radius: 12px !important;
        background: #fafbfc !important;
        padding: 1.5rem !important;
        margin: 1rem 0 !important;
    }}

    /* Sample divider — orange line */
    .sample-divider {{
        display: flex;
        align-items: center;
        gap: 1rem;
        margin: 1.25rem 0 1rem 0;
        color: #666;
        font-size: 0.85rem;
    }}
    .sample-divider::before, .sample-divider::after {{
        content: "";
        flex: 1;
        height: 2px;
        background: {ACCENT_ORANGE};
    }}

    .sample-card {{
        border: 2px solid #e5e7eb;
        border-radius: 10px;
        padding: 1rem 0.75rem;
        text-align: center;
        transition: all 0.2s ease;
        cursor: default;
        background: #fafbfc;
    }}
    .sample-card.active {{
        border-color: {ACCENT_ORANGE};
        background: #fff8f5;
        box-shadow: 0 0 0 3px rgba(241, 90, 36, 0.2);
    }}
    .sample-card .icon {{
        font-size: 1.6rem;
        margin-bottom: 0.35rem;
    }}
    .sample-card .name {{
        font-weight: 600;
        font-size: 0.9rem;
        color: #1a1a1a;
        margin-bottom: 0.15rem;
    }}
    .sample-card .inv-id {{
        font-size: 0.75rem;
        color: #888;
    }}

    /* Sidebar CTA link */
    .sidebar-cta a {{
        color: {ACCENT_ORANGE} !important;
        font-weight: 600;
    }}

    /* Sidebar CTA buttons — CrewAI orange */
    .sidebar-cta-btn {{
        display: block;
        width: 100%;
        text-align: center;
        padding: 0.5rem 1rem;
        border-radius: 8px;
        font-weight: 600;
        font-size: 0.9rem;
        text-decoration: none;
        margin-bottom: 0.5rem;
        box-sizing: border-box;
    }}
    .sidebar-cta-btn.primary {{
        background-color: {ACCENT_ORANGE};
        color: white !important;
        border: 1px solid {ACCENT_ORANGE};
    }}
    .sidebar-cta-btn.primary:hover {{
        background-color: #d94e1a;
        border-color: #d94e1a;
        color: white !important;
    }}
    .sidebar-cta-btn.secondary {{
        background-color: transparent;
        color: {ACCENT_ORANGE} !important;
        border: 1px solid {ACCENT_ORANGE};
    }}
    .sidebar-cta-btn.secondary:hover {{
        background-color: #fff8f5;
        color: #d94e1a !important;
        border-color: #d94e1a;
    }}

    /* Footer — compact */
    .footer-center {{
        display: flex;
        justify-content: center;
        align-items: center;
        gap: 0.5rem;
        flex-wrap: wrap;
        text-align: center;
        color: #999;
        font-size: 0.7rem;
        padding: 0.25rem 0;
        line-height: 1.2;
    }}
</style>
""")


# ── Sidebar ─────────────────────────────────────────────────

with st.sidebar:
    st.logo("app/public/crewai.svg", size="large")
    st.divider()
    st.markdown("**Invoice extraction agent demo**")
    st.markdown(
        "This demo extracts structured data from PDF invoices using CrewAI. "
        "Use a sample below or upload your own to see invoice #, vendor, dates, line items, and totals."
    )
    st.markdown("**The crew processes the invoice as follows:**")
    st.markdown(
        """
        - The PDF is uploaded (or you pick a sample).
        - CrewAI validates it's an invoice and extracts fields: invoice #, vendor, dates, line items, totals.
        - Results appear in a structured box with an option to view raw JSON.
        """
    )
    st.divider()
    st.markdown(
        """
        <a href="https://app.crewai.com/" target="_blank" rel="noopener" class="sidebar-cta-btn primary">Try it on Crew</a>
        <a href="https://github.com/crewAIInc/crewAI" target="_blank" rel="noopener" class="sidebar-cta-btn secondary">See GitHub</a>
        """,
        unsafe_allow_html=True,
    )


# ── Hero ────────────────────────────────────────────────────

st.html("""
<div class="hero">
    <h1>Invoice extraction agent demo</h1>
    <p>Use a sample invoice below, or upload your own PDF. CrewAI will extract the data for you.</p>
</div>
""")


# ── Upload + Run ────────────────────────────────────────────

st.caption("Upload your own invoice")
uploaded_file = st.file_uploader(
    "Choose a PDF file",
    type="pdf",
    label_visibility="collapsed",
)

if uploaded_file is not None:
    st.session_state.selected_sample = None

# ── Sample invoices ─────────────────────────────────────────

st.html('<div class="sample-divider">— or use a sample —</div>')

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

# ── Optional PDF preview (first page as image) ────────────────────────

def _pdf_first_page_image(pdf_bytes: bytes) -> bytes | None:
    """Render first page of PDF as PNG bytes; None if unavailable."""
    if fitz is None:
        return None
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        if len(doc) == 0:
            doc.close()
            return None
        page = doc[0]
        pix = page.get_pixmap(dpi=150)
        png_bytes = pix.tobytes("png")
        doc.close()
        return png_bytes
    except Exception:
        return None


has_input = uploaded_file is not None or st.session_state.selected_sample is not None

run_clicked = st.button(
    "Run Crew",
    type="primary",
    use_container_width=True,
    disabled=(not has_input),
)

# Small optional preview (not part of upload flow — view if you want)
if has_input:
    pdf_for_preview = None
    if uploaded_file is not None:
        pdf_for_preview = uploaded_file.getvalue()
    elif st.session_state.selected_sample is not None:
        sample_path = SAMPLES_DIR / st.session_state.selected_sample["file"]
        pdf_for_preview = sample_path.read_bytes()
    if pdf_for_preview:
        with st.expander("Preview first page", expanded=False):
            img_bytes = _pdf_first_page_image(pdf_for_preview)
            if img_bytes:
                st.image(io.BytesIO(img_bytes), use_container_width=True)
            else:
                st.caption("Preview unavailable.")

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

    st.session_state.last_pdf_bytes = pdf_bytes
    st.session_state.last_pdf_filename = filename

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
        # Optional: view first page again next to results
        if st.session_state.last_pdf_bytes:
            with st.expander("Preview first page (source PDF)", expanded=False):
                img_bytes = _pdf_first_page_image(st.session_state.last_pdf_bytes)
                if img_bytes:
                    st.image(io.BytesIO(img_bytes), use_container_width=True)
                else:
                    st.caption("Preview unavailable.")

        with st.container(border=True):
            st.markdown("**Extracted invoice data**")
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
        CrewAI &copy; 2025 &middot; <a href="https://github.com/crewAIInc/crewAI" target="_blank" rel="noopener" style="color:#999;">GitHub</a>
    </p>
    """)
