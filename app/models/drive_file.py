from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class DriveFile(BaseModel):
    file_id: str
    name: str = ""
    url: str = ""
    last_modified: Optional[datetime] = None
