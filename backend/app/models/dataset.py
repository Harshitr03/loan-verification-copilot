from datetime import datetime, timezone
from typing import Optional
from beanie import Document
from pydantic import Field


class Dataset(Document):
    filename: str
    file_type: str = "loan_tape"
    source_system: str
    uploaded_by: str
    uploaded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    row_count: int = 0
    imported_count: int = 0
    failed_count: int = 0
    status: str = "imported"                 # imported | validated
    column_mapping: dict = Field(default_factory=dict)
    quality_score: Optional[float] = None
    failures: list[dict] = Field(default_factory=list)   # {row_number, reason}

    class Settings:
        name = "datasets"
