#!/usr/bin/env python
"""
doc2data flow: invoice extraction from PDFs.

Triggered by Google Drive (Streamlit uploads) or Gmail. Downloads PDF, extracts text,
validates as invoice, runs ExtractionCrew for structured fields, returns JSON.
"""
import base64
import json
import logging
import os
import re
import tempfile

logging.getLogger("LiteLLM").setLevel(logging.CRITICAL)

from crewai import Agent, LLM
from crewai.flow.flow import Flow, listen, start

from doc2data.crews.extraction_crew.extraction_crew import ExtractionCrew
from doc2data.models import InvoiceFlowState, ValidationResult
from doc2data.tools.invoice_extractor import InvoiceExtractorTool


class InvoiceProcessingFlow(Flow[InvoiceFlowState]):

    @staticmethod
    def _unwrap_trigger(crewai_trigger_payload: dict) -> dict:
        """Normalize trigger payload: AMP wraps data under 'payload', CLI does not."""
        if "payload" in crewai_trigger_payload and isinstance(
            crewai_trigger_payload["payload"], dict
        ):
            data = crewai_trigger_payload["payload"]
        else:
            data = crewai_trigger_payload
        return data

    def _download_pdf_from_gdrive(self, file_id: str) -> str:
        """Download a PDF from Google Drive to a local temp file and return its path."""
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaIoBaseDownload
        from io import BytesIO

        sa_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "")
        if os.path.isfile(sa_json):
            credentials = service_account.Credentials.from_service_account_file(
                sa_json, scopes=["https://www.googleapis.com/auth/drive.readonly"]
            )
        else:
            creds_info = json.loads(sa_json)
            credentials = service_account.Credentials.from_service_account_info(
                creds_info, scopes=["https://www.googleapis.com/auth/drive.readonly"]
            )
        service = build("drive", "v3", credentials=credentials)

        request = service.files().get_media(fileId=file_id, supportsAllDrives=True)
        buffer = BytesIO()
        downloader = MediaIoBaseDownload(buffer, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()

        tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        tmp.write(buffer.getvalue())
        tmp.close()
        return tmp.name

    @start()
    def initialize_flow(self, crewai_trigger_payload: dict = None):
        """Accept AMP trigger payload OR flat API inputs (populated in self.state by the framework)."""
        print("[Flow] initialize_flow started")
        print(f"[Flow] crewai_trigger_payload={'present' if crewai_trigger_payload else 'None'}, "
              f"state.drive_file_id={self.state.drive_file_id!r}, "
              f"state.source_filename={self.state.source_filename!r}")

        if crewai_trigger_payload:
            print(f"[Flow] Raw trigger payload keys: {list(crewai_trigger_payload.keys())}")
            data = self._unwrap_trigger(crewai_trigger_payload)
        elif self.state.drive_file_id:
            data = {
                "drive_file_id": self.state.drive_file_id,
                "source_filename": self.state.source_filename or "upload.pdf",
            }
        else:
            print("[Flow] No inputs received — skipping")
            self.state.extraction_status = "skipped"
            self.state.error_message = "No trigger payload received"
            return

        print(f"[Flow] Resolved data keys: {list(data.keys())}")

        if data.get("drive_file_id"):
            self._initialize_from_gdrive(data)
        else:
            self._initialize_from_gmail(data)

    # ── Google Drive trigger (Streamlit uploads) ────────────────

    def _initialize_from_gdrive(self, data: dict):
        """Download the PDF from Google Drive and populate flow state."""
        self.state.trigger_source = "gdrive"
        self.state.drive_file_id = data["drive_file_id"]
        self.state.source_filename = data.get("source_filename", "upload.pdf")

        print(f"[Flow] GDrive trigger — file_id={self.state.drive_file_id}, filename={self.state.source_filename}")

        try:
            self.state.pdf_path = self._download_pdf_from_gdrive(self.state.drive_file_id)
            file_size = os.path.getsize(self.state.pdf_path)
            print(f"[Flow] PDF downloaded to {self.state.pdf_path} ({file_size} bytes)")
        except Exception as e:
            print(f"[Flow] Failed to download PDF from Google Drive: {e}")
            self.state.extraction_status = "failed"
            self.state.error_message = f"Failed to download PDF from Google Drive: {e}"

    # ── Gmail trigger (future use) ──────────────────────────────

    def _initialize_from_gmail(self, data: dict):
        """Fetch the PDF attachment from Gmail."""
        self.state.trigger_source = "gmail"
        self.state.email_sender = data.get("from", "")
        self.state.email_subject = data.get("subject", "")
        self.state.email_thread_id = (
            data.get("thread_id")
            or data.get("threadId", "")
        )
        self.state.email_message_id = (
            data.get("email_id")
            or data.get("messageId", "")
        )

        print(
            f"[Flow] Gmail trigger — from={self.state.email_sender!r}, "
            f"subject={self.state.email_subject!r}, "
            f"message_id={self.state.email_message_id!r}, "
            f"thread_id={self.state.email_thread_id!r}"
        )

        if not self.state.email_message_id:
            print("[Flow] No message ID in trigger payload — skipping")
            self.state.extraction_status = "skipped"
            self.state.error_message = "No message ID in trigger payload"
            return

        if self.state.email_subject and "invoice" not in self.state.email_subject.lower():
            print(f"[Flow] Subject does not contain 'invoice': '{self.state.email_subject}' — closing flow")
            self.state.extraction_status = "skipped"
            self.state.error_message = "Email subject does not contain 'invoice'"
            return

        gmail_agent = Agent(
            role="Gmail Attachment Fetcher",
            goal="Retrieve the PDF attachment from the incoming email",
            backstory=(
                "You fetch email attachments using the Gmail API. "
                "You always call the tools with the exact parameters provided. "
                "When returning results, include the complete raw JSON response."
            ),
            apps=["gmail"],
            verbose=False,
        )

        print(f"[Flow] Fetching message {self.state.email_message_id}")
        message_result = gmail_agent.kickoff(
            f"Use the google_gmail_get_message tool to retrieve the message. "
            f"Parameters: userId='me', id='{self.state.email_message_id}', format='full'. "
            f"Return the complete raw JSON response as-is, especially the payload.parts "
            f"array with any filename, mimeType, and body.attachmentId fields."
        )

        raw_response = message_result.raw

        attachment_id = None
        filename = None

        att_patterns = [
            r'"attachmentId"\s*:\s*"([^"]+)"',
            r"attachmentId['\"]?\s*[:=]\s*['\"]?([^'\",\s\}]+)",
        ]
        fn_patterns = [
            r'"filename"\s*:\s*"([^"]*\.pdf)"',
            r"filename['\"]?\s*[:=]\s*['\"]?([^\s'\",\}]*\.pdf)",
        ]

        for pattern in att_patterns:
            match = re.search(pattern, raw_response, re.IGNORECASE)
            if match:
                attachment_id = match.group(1)
                break

        for pattern in fn_patterns:
            match = re.search(pattern, raw_response, re.IGNORECASE)
            if match:
                filename = match.group(1)
                break

        if not attachment_id:
            print("[Flow] No PDF attachment found in message — skipping")
            self.state.extraction_status = "skipped"
            self.state.error_message = "No PDF attachment found in email"
            return

        self.state.attachment_filename = filename or "attachment.pdf"
        print(f"[Flow] Found attachment: {self.state.attachment_filename} (id: {attachment_id})")

        get_att_tool = None
        for tool in gmail_agent.tools:
            if "get_attachment" in getattr(tool, "name", ""):
                get_att_tool = tool
                break

        if get_att_tool:
            print("[Flow] Fetching attachment via direct tool call")
            try:
                att_raw = get_att_tool._run(
                    userId="me",
                    messageId=self.state.email_message_id,
                    id=attachment_id,
                )
                att_data = json.loads(att_raw) if isinstance(att_raw, str) else att_raw
                result_obj = att_data.get("result", att_data)
                b64_data = result_obj.get("data", "")
            except Exception as e:
                print(f"[Flow] Direct tool call failed ({e}), falling back to agent")
                get_att_tool = None

        if not get_att_tool:
            print("[Flow] Fetching attachment via agent kickoff (fallback)")
            att_result = gmail_agent.kickoff(
                f"Use the google_gmail_get_attachment tool. "
                f"Parameters: userId='me', messageId='{self.state.email_message_id}', "
                f"id='{attachment_id}'. "
                f"Return the complete raw JSON response including the data field."
            )
            b64_match = re.search(
                r'"data"\s*:\s*"([A-Za-z0-9+/=_-]+)"', att_result.raw
            )
            b64_data = b64_match.group(1) if b64_match else att_result.raw.strip()

        try:
            if not b64_data:
                raise ValueError("No base64 data received from attachment fetch")

            b64_data = b64_data.replace("-", "+").replace("_", "/")
            pdf_bytes = base64.b64decode(b64_data)

            tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
            tmp.write(pdf_bytes)
            tmp.close()
            self.state.pdf_path = tmp.name
            print(f"[Flow] PDF saved to {self.state.pdf_path} ({len(pdf_bytes)} bytes)")

        except Exception as e:
            print(f"[Flow] Failed to decode/save attachment: {e}")
            self.state.extraction_status = "failed"
            self.state.error_message = f"Failed to decode attachment: {e}"

    @listen(initialize_flow)
    def extract_pdf_text(self):
        """Agent uses InvoiceExtractorTool to pull raw text from the PDF."""
        if self.state.extraction_status in ("skipped", "failed"):
            return

        print("[Flow] extract_pdf_text started")
        extractor_agent = Agent(
            role="PDF Text Extractor",
            goal="Extract all raw text content from PDF invoices",
            backstory=(
                "You extract text from PDF files using the invoice_extractor tool. "
                "You return the raw_extracted_text field from the tool output verbatim, "
                "without summarizing or modifying any content."
            ),
            tools=[InvoiceExtractorTool()],
            llm=LLM(model="groq/llama-3.3-70b-versatile", temperature=0),
            verbose=False,
        )

        result = extractor_agent.kickoff(
            f"Extract all text from the PDF at path: {self.state.pdf_path}\n\n"
            f"Use the invoice_extractor tool with pdf_path='{self.state.pdf_path}'.\n"
            f"Return ONLY the raw_extracted_text field from the tool output. "
            f"Do not summarize, reformat, or omit any text — return it exactly as-is."
        )

        self.state.pdf_raw_text = result.raw.strip() if result.raw else ""

        if not self.state.pdf_raw_text:
            print("[Flow] Extraction returned empty text — failing")
            self.state.extraction_status = "failed"
            self.state.error_message = "Invoice extractor returned no text from the PDF"

    @listen(extract_pdf_text)
    def validate_invoice(self):
        """Direct Agent.kickoff() to determine if the PDF is a real invoice."""
        if self.state.extraction_status in ("skipped", "failed"):
            return

        print("[Flow] validate_invoice started")
        validator = Agent(
            role="Invoice Validator",
            goal="Determine if a PDF contains a real, processable invoice",
            backstory="You review extracted invoice text and make a binary determination.",
            llm=LLM(model="groq/llama-3.3-70b-versatile", temperature=0),
            verbose=False,
        )

        result = validator.kickoff(
            f"Review the following text extracted from a PDF.\n"
            f"Determine if this is a real, complete invoice with:\n"
            f"- At least one line item\n"
            f"- A non-zero total amount\n"
            f"- An identifiable vendor or bill-to party\n\n"
            f"Return is_valid_invoice=False for blank documents, test files, or "
            f"documents with $0.00 total and no line items.\n\n"
            f"Text:\n{self.state.pdf_raw_text}",
            response_format=ValidationResult,
        )

        validation = result.pydantic
        self.state.is_valid_invoice = validation.is_valid_invoice

        if not validation.is_valid_invoice:
            print(f"[Flow] Invoice validation failed: {validation.reason}")
            self.state.extraction_status = "skipped"
            self.state.error_message = validation.reason

    @listen(validate_invoice)
    def extract_invoice_data(self):
        """Kick off ExtractionCrew to get structured invoice fields."""
        if self.state.extraction_status in ("skipped", "failed"):
            return

        print("[Flow] extract_invoice_data started")
        crew_output = (
            ExtractionCrew()
            .crew()
            .kickoff(inputs={"pdf_raw_text": self.state.pdf_raw_text})
        )

        if crew_output.pydantic:
            self.state.invoice_data = crew_output.pydantic.model_dump()
        else:
            self.state.invoice_data = crew_output.json_dict or {}

        if not self.state.invoice_data:
            self.state.extraction_status = "failed"
            self.state.error_message = "ExtractionCrew returned empty data"

    @listen(extract_invoice_data)
    def finalize(self):
        """Return the extracted invoice data as the flow's final output."""
        if self.state.extraction_status not in ("skipped", "failed"):
            self.state.extraction_status = "processed"

        result = {
            "extraction_status": self.state.extraction_status,
            "invoice_data": self.state.invoice_data,
            "error_message": self.state.error_message or None,
        }

        print(f"[Flow] finalize — status={self.state.extraction_status}")
        if self.state.invoice_data:
            data = self.state.invoice_data
            print(f"[Flow]   Invoice #: {data.get('invoice_number')}")
            print(f"[Flow]   Vendor:    {data.get('vendor_name')}")
            print(f"[Flow]   Total:     {data.get('currency', 'USD')} {data.get('total_amount')}")

        return result


def kickoff():
    flow = InvoiceProcessingFlow()
    flow.kickoff()


def plot():
    flow = InvoiceProcessingFlow()
    flow.plot()


def run_with_trigger():
    """Run the flow with a trigger payload from CLI."""
    import sys

    if len(sys.argv) < 2:
        raise Exception(
            "No trigger payload provided. Please provide JSON payload as argument."
        )

    try:
        trigger_payload = json.loads(sys.argv[1])
    except json.JSONDecodeError:
        raise Exception("Invalid JSON payload provided as argument")

    flow = InvoiceProcessingFlow()
    try:
        result = flow.kickoff({"crewai_trigger_payload": trigger_payload})
        return result
    except Exception as e:
        raise Exception(f"An error occurred while running the flow with trigger: {e}")


def run_gdrive():
    """Run the full flow against a PDF already uploaded to Google Drive.

    Usage:  uv run run_gdrive <drive_file_id> [source_filename]

    This simulates what CrewAI Enterprise receives when Streamlit triggers a run.
    Requires GOOGLE_SERVICE_ACCOUNT_JSON and GOOGLE_DRIVE_FOLDER_ID in .env.
    """
    import sys

    from dotenv import load_dotenv

    load_dotenv()

    if len(sys.argv) < 2:
        print("Usage: uv run run_gdrive <drive_file_id> [source_filename]")
        print("\nProvide the Google Drive file ID of an uploaded PDF.")
        print("You can find it in the Drive URL or from the Streamlit upload logs.")
        sys.exit(1)

    drive_file_id = sys.argv[1]
    source_filename = sys.argv[2] if len(sys.argv) >= 3 else "upload.pdf"

    print(f"\n{'='*60}")
    print(f"[GDrive Run] file_id={drive_file_id}")
    print(f"[GDrive Run] filename={source_filename}")
    print(f"{'='*60}\n")

    flow = InvoiceProcessingFlow()
    result = flow.kickoff({
        "drive_file_id": drive_file_id,
        "source_filename": source_filename,
    })

    print(f"\n{'='*60}")
    print("[GDrive Run] Flow complete!")
    print(f"  Status:     {flow.state.extraction_status}")
    if flow.state.invoice_data:
        data = flow.state.invoice_data
        print(f"  Invoice #:  {data.get('invoice_number')}")
        print(f"  Vendor:     {data.get('vendor_name')}")
        print(f"  Total:      {data.get('currency', 'USD')} {data.get('total_amount')}")
    if flow.state.error_message:
        print(f"  Error:      {flow.state.error_message}")
    print(f"{'='*60}")

    return result


def run_local():
    """Run the core pipeline against a local PDF (no Gmail, no Drive).

    Usage:  uv run run_local [path/to/invoice.pdf]
    If no path given, uses the first PDF in app/public/samples/.
    """
    import sys
    from pathlib import Path

    if len(sys.argv) >= 2 and not sys.argv[1].startswith("-"):
        sample_pdf = Path(sys.argv[1]).resolve()
    else:
        sample_dir = Path(__file__).resolve().parents[2] / "app" / "public" / "samples"
        pdfs = sorted(sample_dir.glob("*.pdf")) if sample_dir.exists() else []
        if not pdfs:
            raise FileNotFoundError(
                f"No PDFs found. Either pass a path as argument or add a PDF to {sample_dir}"
            )
        sample_pdf = pdfs[0]

    if not sample_pdf.exists():
        raise FileNotFoundError(f"PDF not found: {sample_pdf}")

    pdf_path = str(sample_pdf)
    print(f"\n{'='*60}")
    print(f"[Local Run] PDF: {sample_pdf.name}")
    print(f"{'='*60}\n")

    # --- Step 1: Agent + InvoiceExtractorTool ---
    print("[Step 1/5] Extracting text via PDF Text Extractor agent...")
    extractor_agent = Agent(
        role="PDF Text Extractor",
        goal="Extract all raw text content from PDF invoices",
        backstory=(
            "You extract text from PDF files using the invoice_extractor tool. "
            "You return the raw_extracted_text field from the tool output verbatim, "
            "without summarizing or modifying any content."
        ),
        tools=[InvoiceExtractorTool()],
        llm=LLM(model="groq/llama-3.3-70b-versatile", temperature=0),
        verbose=False,
    )
    extract_result = extractor_agent.kickoff(
        f"Extract all text from the PDF at path: {pdf_path}\n\n"
        f"Use the invoice_extractor tool with pdf_path='{pdf_path}'.\n"
        f"Return ONLY the raw_extracted_text field from the tool output. "
        f"Do not summarize, reformat, or omit any text — return it exactly as-is."
    )
    pdf_raw_text = extract_result.raw.strip()
    print(f"  -> Extracted {len(pdf_raw_text)} chars of text")
    if not pdf_raw_text:
        print("  !! No text extracted — aborting")
        return
    print(f"  -> Preview: {pdf_raw_text[:200]}...\n")

    # --- Step 2: Agent + Structured Output (Validation) ---
    print("[Step 2/5] Validating invoice via Invoice Validator agent...")
    validator = Agent(
        role="Invoice Validator",
        goal="Determine if a PDF contains a real, processable invoice",
        backstory="You review extracted invoice text and make a binary determination.",
        llm=LLM(model="groq/llama-3.3-70b-versatile", temperature=0),
        verbose=False,
    )
    val_result = validator.kickoff(
        f"Review the following text extracted from a PDF.\n"
        f"Determine if this is a real, complete invoice with:\n"
        f"- At least one line item\n"
        f"- A non-zero total amount\n"
        f"- An identifiable vendor or bill-to party\n\n"
        f"Return is_valid_invoice=False for blank documents, test files, or "
        f"documents with $0.00 total and no line items.\n\n"
        f"Text:\n{pdf_raw_text}",
        response_format=ValidationResult,
    )
    validation = val_result.pydantic
    print(f"  -> is_valid_invoice={validation.is_valid_invoice}, reason={validation.reason!r}\n")
    if not validation.is_valid_invoice:
        print("  !! Validation failed — aborting")
        return

    # --- Step 3: Full Crew (Agent + Task + Guardrail) ---
    print("[Step 3/5] Extracting structured data via ExtractionCrew...")
    crew_output = (
        ExtractionCrew()
        .crew()
        .kickoff(inputs={"pdf_raw_text": pdf_raw_text})
    )
    if crew_output.pydantic:
        invoice_data = crew_output.pydantic.model_dump()
    else:
        invoice_data = crew_output.json_dict or {}

    if not invoice_data:
        print("  !! ExtractionCrew returned empty data — aborting")
        return

    print(f"  -> Invoice #: {invoice_data.get('invoice_number')}")
    print(f"  -> Vendor: {invoice_data.get('vendor_name')}")
    print(f"  -> Total: {invoice_data.get('currency', 'USD')} {invoice_data.get('total_amount')}")
    print(f"  -> Line items: {len(invoice_data.get('line_items', []))}\n")

    # --- Step 4: Summary ---
    print(f"{'='*60}")
    print("[Step 4/4] Local run complete!")
    print(f"  PDF:        {sample_pdf.name}")
    print(f"  Invoice #:  {invoice_data.get('invoice_number')}")
    print(f"  Vendor:     {invoice_data.get('vendor_name')}")
    print(f"  Total:      {invoice_data.get('currency', 'USD')} {invoice_data.get('total_amount')}")
    print(f"{'='*60}")
    print("\nFull extracted data:")
    print(json.dumps(invoice_data, indent=2, default=str))


if __name__ == "__main__":
    kickoff()
