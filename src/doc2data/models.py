from datetime import date
from typing import Optional

from pydantic import BaseModel


class LineItem(BaseModel):
    description: str
    quantity: float
    rate: float
    amount: float


class InvoiceRecord(BaseModel):
    invoice_number: Optional[str] = None
    vendor_name: Optional[str] = None
    bill_to_name: Optional[str] = None
    bill_to_address: Optional[str] = None
    ship_to_address: Optional[str] = None
    invoice_date: Optional[date] = None
    due_date: Optional[date] = None
    ship_mode: Optional[str] = None
    line_items: list[LineItem] = []
    subtotal: Optional[float] = None
    discount_percent: Optional[float] = None
    discount_amount: Optional[float] = None
    shipping_cost: Optional[float] = None
    tax_amount: Optional[float] = None
    total_amount: Optional[float] = None
    currency: str = "USD"
    order_id: Optional[str] = None


class InvoiceFlowState(BaseModel):
    # Trigger inputs
    email_sender: str = ""
    email_subject: str = ""
    email_thread_id: str = ""
    email_message_id: str = ""
    attachment_filename: str = ""

    # Processing
    pdf_path: str = ""
    pdf_raw_text: str = ""
    is_valid_invoice: bool = False

    # Extraction output
    invoice_data: dict = {}

    # Final state
    db_record_id: Optional[int] = None
    extraction_status: str = "pending"
    error_message: str = ""


class ValidationResult(BaseModel):
    is_valid_invoice: bool
    reason: str


class DBWriteResult(BaseModel):
    success: bool
    record_id: Optional[int] = None
    error_detail: Optional[str] = None
