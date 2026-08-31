from typing import Optional
from beanie import Document
from pydantic import Field
import pymongo


class RawRecord(Document):
    dataset_id: str
    row_number: int
    raw: dict = Field(default_factory=dict)
    source_file: Optional[str] = None
    file_type: str = "loan_tape"             # loan_tape | servicer_update | document_manifest

    class Settings:
        name = "raw_records"
        indexes = [[("dataset_id", pymongo.ASCENDING)]]
