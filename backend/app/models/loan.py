from datetime import date
from typing import Optional
from beanie import Document
from backend.app.models.types import Money
import pymongo


class Loan(Document):
    loan_id: str
    dataset_id: str
    borrower_id: Optional[str] = None
    loan_type: Optional[str] = None
    origination_date: Optional[date] = None
    maturity_date: Optional[date] = None
    original_principal: Optional[Money] = None
    current_balance: Optional[Money] = None
    interest_rate: Optional[Money] = None
    term_months: Optional[int] = None
    borrower_state: Optional[str] = None
    loan_purpose: Optional[str] = None
    credit_grade: Optional[str] = None
    employment_length: Optional[str] = None
    income_band: Optional[str] = None
    payment_status: Optional[str] = None
    days_past_due: Optional[int] = None
    servicer_name: Optional[str] = None
    last_payment_date: Optional[date] = None
    last_updated_at: Optional[date] = None     # date-precision across all sources (see stale_record)
    document_status: Optional[str] = None
    source_system: Optional[str] = None
    normalized_from_raw_id: Optional[str] = None
    validation_status: str = "pending"        # pending|validated
    lifecycle_state: str = "imported"          # imported|validated|in_review|verified|rejected

    class Settings:
        name = "loans"
        indexes = [[("loan_id", pymongo.ASCENDING)]]
