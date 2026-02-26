from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel

from models.drive_file import DriveFile


class Execution(BaseModel):
    uuid: str
    input_file: Optional[DriveFile] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    status: Optional[str] = "pending"
    invoice_data: Optional[dict[str, Any]] = None
    db_record_id: Optional[int] = None
    error_message: Optional[str] = None
