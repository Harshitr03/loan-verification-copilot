from datetime import datetime
from typing import Optional
from beanie import Document
from pydantic import Field
import pymongo


class VerifiedRecord(Document):
    seq: int                                 # chain order (finding 1c)
    loan_id: str
    canonical_data: dict = Field(default_factory=dict)   # string-serialized (BSON-stable)
    source_file_ref: Optional[str] = None
    validation_result: dict = Field(default_factory=dict)
    reviewer_decision: Optional[dict] = None
    ai_recommendation_ref: Optional[str] = None
    verified_at: datetime                    # queryable datetime (unhashed)
    ts_iso: str                              # hashed timestamp string
    verified_by: str
    record_hash: str
    prev_record_hash: Optional[str] = None

    class Settings:
        name = "verified_records"
        indexes = [
            [("loan_id", pymongo.ASCENDING)],
            [("seq", pymongo.ASCENDING)],
        ]
