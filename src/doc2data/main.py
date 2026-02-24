#!/usr/bin/env python
import base64
import json
import re
import tempfile
from datetime import datetime, timezone

from crewai import Agent, LLM
from crewai.flow.flow import Flow, listen, start

from doc2data.crews.extraction_crew.extraction_crew import ExtractionCrew
from doc2data.models import DBWriteResult, InvoiceFlowState, ValidationResult
from doc2data.tools.db_writer import DBWriterTool
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

    @start()
    def initialize_flow(self, crewai_trigger_payload: dict = None):
        """Extract trigger metadata and fetch the PDF attachment via Gmail agent."""
        print("[Flow] initialize_flow started")

        if not crewai_trigger_payload:
            print("[Flow] No trigger payload — skipping")
            self.state.extraction_status = "skipped"
            self.state.error_message = "No trigger payload received"
            return

        print(f"[Flow] Raw trigger payload keys: {list(crewai_trigger_payload.keys())}")
        print(f"[Flow] Raw trigger payload: {json.dumps(crewai_trigger_payload, default=str)[:2000]}")

        data = self._unwrap_trigger(crewai_trigger_payload)
        print(f"[Flow] Unwrapped data keys: {list(data.keys())}")

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
            f"[Flow] Parsed — from={self.state.email_sender!r}, "
            f"subject={self.state.email_subject!r}, "
            f"message_id={self.state.email_message_id!r}, "
            f"thread_id={self.state.email_thread_id!r}"
        )

        if not self.state.email_message_id:
            print("[Flow] No message ID in trigger payload — skipping")
            self.state.extraction_status = "skipped"
            self.state.error_message = "No message ID in trigger payload"
            return

        # Gate: subject must contain "invoice" (case-insensitive)
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

        # Step 1: Fetch the full message via agent kickoff (also initializes platform tools)
        print(f"[Flow] Fetching message {self.state.email_message_id}")
        message_result = gmail_agent.kickoff(
            f"Use the google_gmail_get_message tool to retrieve the message. "
            f"Parameters: userId='me', id='{self.state.email_message_id}', format='full'. "
            f"Return the complete raw JSON response as-is, especially the payload.parts "
            f"array with any filename, mimeType, and body.attachmentId fields."
        )

        # Parse attachment metadata from the agent's response
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

        # Step 2: Fetch attachment binary data via direct tool call (no LLM)
        # After the first kickoff, platform tools are now initialized on the agent
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
            # Fallback: use agent kickoff for attachment fetch
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

            # Gmail uses URL-safe base64
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
            llm=LLM(model="openai/gpt-4o-mini", temperature=0),
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
            llm=LLM(model="openai/gpt-4o-mini", temperature=0),
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
    def write_to_database(self):
        """Agent uses DBWriterTool to insert the extracted invoice into Postgres."""
        if self.state.extraction_status in ("skipped", "failed"):
            return

        print("[Flow] write_to_database started")

        record = dict(self.state.invoice_data)
        if "line_items" in record and isinstance(record["line_items"], list):
            record["line_items"] = json.dumps(
                [
                    item if isinstance(item, dict) else item
                    for item in record["line_items"]
                ]
            )
        record["source_email"] = self.state.email_sender
        record["source_filename"] = self.state.attachment_filename
        record["raw_extracted_text"] = self.state.pdf_raw_text
        record["extraction_status"] = "processed"

        db_agent = Agent(
            role="Database Writer",
            goal="Write structured invoice records to the PostgreSQL database",
            backstory=(
                "You persist invoice data to a PostgreSQL database using the db_writer tool. "
                "You always pass the record exactly as provided without modification."
            ),
            tools=[DBWriterTool()],
            llm=LLM(model="openai/gpt-4o-mini", temperature=0),
            verbose=False,
        )

        record_json = json.dumps(record, default=str)
        result = db_agent.kickoff(
            f"Write this invoice record to the database using the db_writer tool.\n"
            f"Pass the following JSON string as the 'record_json' parameter exactly as-is:\n\n"
            f"{record_json}\n\n"
            f"Return whether the write succeeded, the record_id, and any error.",
            response_format=DBWriteResult,
        )

        db_result = result.pydantic
        if db_result.success:
            self.state.db_record_id = db_result.record_id
            self.state.extraction_status = "processed"
            print(f"[Flow] DB record created: id={db_result.record_id}")
        else:
            self.state.extraction_status = "failed"
            self.state.error_message = db_result.error_detail or "DB write failed"
            print(f"[Flow] DB write failed: {db_result.error_detail}")

    @listen(write_to_database)
    def finalize(self):
        """Send a confirmation reply email on the original Gmail thread."""
        print(f"[Flow] finalize — status={self.state.extraction_status}")

        if not self.state.email_thread_id:
            print("[Flow] No thread ID — skipping email reply")
            return

        email_agent = Agent(
            role="Email Responder",
            goal="Send a confirmation reply on the original email thread",
            backstory="You send concise status emails about invoice processing results.",
            apps=["gmail/send_email"],
            verbose=False,
        )

        subject = f"Re: {self.state.email_subject}"
        body = self._build_reply_body()

        email_agent.kickoff(
            f"Send an email reply with the following details:\n"
            f"- to: {self.state.email_sender}\n"
            f"- subject: {subject}\n"
            f"- body: {body}\n"
            f"- threadId: {self.state.email_thread_id}\n"
            f"- userId: me\n\n"
            f"Send this email now as an inline thread reply."
        )
        print("[Flow] Confirmation email sent")

    @staticmethod
    def _find_pdf_attachment(msg_data: dict) -> tuple[str | None, str | None]:
        """Walk Gmail message parts to find the first PDF attachment.

        Returns (attachment_id, filename) or (None, None).
        """
        result = msg_data.get("result", msg_data)
        if "error" in result:
            return None, None

        payload = result.get("payload", {})

        def search_parts(parts: list) -> tuple[str | None, str | None]:
            for part in parts:
                fname = part.get("filename", "")
                mime = part.get("mimeType", "")
                body = part.get("body", {})
                att_id = body.get("attachmentId")

                if att_id and fname.lower().endswith(".pdf"):
                    return att_id, fname
                if att_id and mime == "application/pdf":
                    return att_id, fname or "attachment.pdf"

                nested = part.get("parts", [])
                if nested:
                    found = search_parts(nested)
                    if found[0]:
                        return found
            return None, None

        # Check top-level payload body
        top_body = payload.get("body", {})
        top_att = top_body.get("attachmentId")
        top_fn = payload.get("filename", "")
        if top_att and (
            top_fn.lower().endswith(".pdf")
            or payload.get("mimeType") == "application/pdf"
        ):
            return top_att, top_fn or "attachment.pdf"

        return search_parts(payload.get("parts", []))

    def _build_reply_body(self) -> str:
        status = self.state.extraction_status

        if status == "processed":
            data = self.state.invoice_data
            now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            line_count = len(data.get("line_items", []))
            return (
                f"Hi,\n\n"
                f"Your invoice has been successfully processed and logged.\n\n"
                f"Summary:\n"
                f"- Invoice #: {data.get('invoice_number', 'N/A')}\n"
                f"- Vendor: {data.get('vendor_name', 'N/A')}\n"
                f"- Invoice Date: {data.get('invoice_date', 'N/A')}\n"
                f"- Line Items: {line_count}\n"
                f"- Total Amount: {data.get('currency', 'USD')} {data.get('total_amount', 'N/A')}\n"
                f"- Order ID: {data.get('order_id') or 'N/A'}\n"
                f"- Record ID: {self.state.db_record_id}\n"
                f"- Processed At: {now}\n\n"
                f"No further action required.\n\n"
                f"—Invoice Processing Flow | Doc 2 Data Demo"
            )

        elif status == "skipped":
            return (
                f"Hi,\n\n"
                f"The attached PDF does not appear to contain a valid invoice.\n"
                f"No record was created.\n\n"
                f"Reason: The document was blank, had no line items, or had a $0.00 total.\n\n"
                f"Please reply with a valid invoice PDF if you intended to submit one.\n\n"
                f"—Invoice Processing Flow | Doc 2 Data Demo"
            )

        else:  # failed
            return (
                f"Hi,\n\n"
                f"We encountered an error while processing your invoice attachment.\n"
                f"No record was created.\n\n"
                f"Error detail: {self.state.error_message}\n\n"
                f"Please contact your administrator or retry with a different file.\n\n"
                f"—Invoice Processing Flow | Doc 2 Data Demo"
            )


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


def run_local():
    """Run the core pipeline against a local sample invoice PDF (no Gmail)."""
    from pathlib import Path

    sample_pdf = Path(__file__).resolve().parents[2] / "local_files" / "sample_invoices" / "invoice_Aaron Bergman_36259.pdf"
    if not sample_pdf.exists():
        raise FileNotFoundError(f"Sample PDF not found: {sample_pdf}")

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
        llm=LLM(model="openai/gpt-4o-mini", temperature=0),
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
        llm=LLM(model="openai/gpt-4o-mini", temperature=0),
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

    # --- Step 4: Agent + DBWriterTool ---
    print("[Step 4/5] Writing to database via Database Writer agent...")
    record = dict(invoice_data)
    if "line_items" in record and isinstance(record["line_items"], list):
        record["line_items"] = json.dumps(
            [item if isinstance(item, dict) else item for item in record["line_items"]]
        )
    record["source_email"] = "local_test@example.com"
    record["source_filename"] = sample_pdf.name
    record["raw_extracted_text"] = pdf_raw_text
    record["extraction_status"] = "processed"

    db_agent = Agent(
        role="Database Writer",
        goal="Write structured invoice records to the PostgreSQL database",
        backstory=(
            "You persist invoice data to a PostgreSQL database using the db_writer tool. "
            "You always pass the record exactly as provided without modification."
        ),
        tools=[DBWriterTool()],
        llm=LLM(model="openai/gpt-4o-mini", temperature=0),
        verbose=False,
    )
    record_json = json.dumps(record, default=str)
    db_result_raw = db_agent.kickoff(
        f"Write this invoice record to the database using the db_writer tool.\n"
        f"Pass the following JSON string as the 'record_json' parameter exactly as-is:\n\n"
        f"{record_json}\n\n"
        f"Return whether the write succeeded, the record_id, and any error.",
        response_format=DBWriteResult,
    )
    db_result = db_result_raw.pydantic
    if db_result.success:
        print(f"  -> DB record created: id={db_result.record_id}\n")
    else:
        print(f"  !! DB write failed: {db_result.error_detail}\n")
        return

    # --- Step 5: Summary ---
    print(f"{'='*60}")
    print("[Step 5/5] Local run complete!")
    print(f"  PDF:        {sample_pdf.name}")
    print(f"  Invoice #:  {invoice_data.get('invoice_number')}")
    print(f"  Vendor:     {invoice_data.get('vendor_name')}")
    print(f"  Total:      {invoice_data.get('currency', 'USD')} {invoice_data.get('total_amount')}")
    print(f"  DB Record:  {db_result.record_id}")
    print(f"{'='*60}")


if __name__ == "__main__":
    kickoff()
