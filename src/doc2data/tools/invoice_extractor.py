import re
from typing import Any, Type

import pdfplumber
from dateutil import parser as date_parser
from pydantic import BaseModel, Field

from crewai.tools import BaseTool


class ExtractorInput(BaseModel):
    """Input schema for InvoiceExtractorTool."""

    pdf_path: str = Field(..., description="Absolute path to the PDF file to extract")


def _clean_currency(value: str) -> float | None:
    """Strip $, commas, and whitespace then cast to float."""
    cleaned = re.sub(r"[$,\s]", "", value)
    try:
        return float(cleaned)
    except (ValueError, TypeError):
        return None


def _parse_date(text: str) -> str | None:
    """Parse a date string and return ISO format, or None."""
    try:
        return date_parser.parse(text.strip()).date().isoformat()
    except (ValueError, TypeError):
        return None


def _parse_line_items(text: str) -> list[dict[str, Any]]:
    """Extract line items from the text block between the header row and Subtotal."""
    items: list[dict[str, Any]] = []
    header_match = re.search(r"Item\s+Quantity\s+Rate\s+Amount", text)
    subtotal_match = re.search(r"Subtotal:", text)
    if not header_match or not subtotal_match:
        return items

    block = text[header_match.end() : subtotal_match.start()]
    lines = [ln.strip() for ln in block.strip().splitlines() if ln.strip()]

    i = 0
    while i < len(lines):
        line = lines[i]
        # Line item rows end with a pattern like:  <qty> $<rate> $<amount>
        match = re.search(
            r"^(.+?)\s+(\d+)\s+\$([\d,]+\.?\d*)\s+\$([\d,]+\.?\d*)\s*$", line
        )
        if match:
            items.append(
                {
                    "description": match.group(1).strip(),
                    "quantity": float(match.group(2)),
                    "rate": _clean_currency(match.group(3)),
                    "amount": _clean_currency(match.group(4)),
                }
            )
        i += 1

    return items


class InvoiceExtractorTool(BaseTool):
    name: str = "invoice_extractor"
    description: str = (
        "Extracts raw text and structured invoice data from a PDF file "
        "using pdfplumber. Returns a dict with all invoice fields."
    )
    args_schema: Type[BaseModel] = ExtractorInput

    def _run(self, pdf_path: str) -> dict[str, Any]:
        result: dict[str, Any] = {
            "invoice_number": None,
            "vendor_name": None,
            "bill_to_name": None,
            "bill_to_address": None,
            "ship_to_address": None,
            "invoice_date": None,
            "due_date": None,
            "ship_mode": None,
            "line_items": [],
            "subtotal": None,
            "discount_percent": None,
            "discount_amount": None,
            "shipping_cost": None,
            "tax_amount": None,
            "total_amount": None,
            "currency": "USD",
            "order_id": None,
            "raw_extracted_text": "",
            "extraction_status": "processed",
        }

        try:
            full_text = ""
            with pdfplumber.open(pdf_path) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text() or ""
                    full_text += page_text + "\n"

            full_text = full_text.strip()
            result["raw_extracted_text"] = full_text

            if not full_text:
                result["extraction_status"] = "failed"
                return result

            # Vendor name (top of invoice before "INVOICE")
            if "SuperStore" in full_text:
                result["vendor_name"] = "SuperStore"

            # Invoice number
            inv_match = re.search(r"#\s*(\d+)", full_text)
            if inv_match:
                result["invoice_number"] = inv_match.group(1)

            # Date
            date_match = re.search(r"Date:\s*(.+?)$", full_text, re.MULTILINE)
            if date_match:
                result["invoice_date"] = _parse_date(date_match.group(1))

            # Ship Mode
            ship_mode_match = re.search(r"Ship Mode:\s*(.+?)$", full_text, re.MULTILINE)
            if ship_mode_match:
                result["ship_mode"] = ship_mode_match.group(1).strip()

            # Bill To name: the line after "Bill To: Ship To:" or "Bill To:"
            # In these invoices, the name appears on a line between "Ship Mode" and "Balance Due"
            bill_to_match = re.search(
                r"Ship Mode:.*?\n(.+?)(?:\s+\d{5}|\s+Balance)", full_text, re.DOTALL
            )
            if bill_to_match:
                name_line = bill_to_match.group(1).strip().splitlines()[0].strip()
                result["bill_to_name"] = name_line

            # Ship To address: zip, city, state, country pattern after the name
            addr_match = re.search(
                r"(\d{5},\s*.+?)(?:Balance Due|Item\s+Quantity)",
                full_text,
                re.DOTALL,
            )
            if addr_match:
                addr = " ".join(addr_match.group(1).split())
                result["ship_to_address"] = addr.strip().rstrip(",")

            # Balance Due / Total
            total_match = re.search(r"Total:\s*\$([\d,]+\.?\d*)", full_text)
            if total_match:
                result["total_amount"] = _clean_currency(total_match.group(1))

            # Subtotal
            subtotal_match = re.search(r"Subtotal:\s*\$([\d,]+\.?\d*)", full_text)
            if subtotal_match:
                result["subtotal"] = _clean_currency(subtotal_match.group(1))

            # Discount
            discount_match = re.search(
                r"Discount\s*\((\d+)%\):\s*\$([\d,]+\.?\d*)", full_text
            )
            if discount_match:
                result["discount_percent"] = float(discount_match.group(1))
                result["discount_amount"] = _clean_currency(discount_match.group(2))

            # Shipping
            shipping_match = re.search(r"Shipping:\s*\$([\d,]+\.?\d*)", full_text)
            if shipping_match:
                result["shipping_cost"] = _clean_currency(shipping_match.group(1))

            # Line items
            result["line_items"] = _parse_line_items(full_text)

            # Order ID
            order_match = re.search(r"Order ID\s*:\s*(.+?)$", full_text, re.MULTILINE)
            if order_match:
                result["order_id"] = order_match.group(1).strip()

        except Exception as e:
            result["extraction_status"] = "failed"
            result["raw_extracted_text"] = f"Error during extraction: {e}"

        return result
