from typing import Optional
from beanie import Document
import pymongo


class Exception(Document):
    loan_id: str
    loan_ref: Optional[str] = None           # the exact Loan._id (distinguishes duplicate_loan_id pair)
    dataset_id: str
    rule_id: str
    type: str                                # ROW | DATASET
    severity: str                            # low | medium | high | critical
    source: str = "rule"                     # rule | ml | reconciliation
    field: Optional[str] = None
    observed_value: Optional[str] = None
    expected: Optional[str] = None
    sibling_value: Optional[str] = None
    message: str = ""
    status: str = "open"                     # open | resolved | accepted | rejected
    ai_recommendation_id: Optional[str] = None
    resolution: Optional[dict] = None        # {action, old_value, new_value, by, at}

    class Settings:
        name = "exceptions"
        indexes = [
            [("status", pymongo.ASCENDING)],
            [("severity", pymongo.ASCENDING)],
            [("type", pymongo.ASCENDING)],
        ]
