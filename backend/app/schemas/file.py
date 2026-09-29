from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel


class FileUploadResponse(BaseModel):
    file_id: int
    original_filename: str
    detected_columns: List[str]
    row_count: int
    term_label: Optional[str] = None


class FileRecord(BaseModel):
    id: int
    original_filename: str
    stored_filename: str
    term_label: Optional[str]
    detected_columns: Optional[List[str]]
    row_count: Optional[int]
    upload_time: datetime

    model_config = {"from_attributes": True}


class FileTermUpdate(BaseModel):
    term_label: str
