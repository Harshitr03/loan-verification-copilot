from datetime import date
from decimal import Decimal
from backend.app.ingestion.normalize import to_canonical


def test_normalizes_messy_row():
    raw = {"loan_id": " LN1 ", "borrower_id": "BR1", "loan_type": "Fixed",
           "origination_date": "01/15/2020", "original_principal": "$250,000.00",
           "borrower_state": "California", "interest_rate": "5.25%", "payment_status": "current"}
    canon, reason = to_canonical(raw, "ORIG_SYS")
    assert reason is None
    assert canon["loan_id"] == "LN1" and canon["loan_type"] == "FIXED"
    assert canon["origination_date"] == date(2020, 1, 15)
    assert canon["original_principal"] == Decimal("250000.00")
    assert canon["borrower_state"] == "CA" and canon["interest_rate"] == Decimal("5.25")
    assert canon["payment_status"] == "CURRENT" and canon["source_system"] == "ORIG_SYS"


def test_already_canonical_generated_tape_row_is_near_identity():
    raw = {"loan_id": "LN00001", "loan_type": "FIXED", "origination_date": "2020-01-15",
           "original_principal": "250000.00", "borrower_state": "CA", "interest_rate": "5.25",
           "payment_status": "CURRENT", "current_balance": "200000.00", "days_past_due": "0"}
    canon, reason = to_canonical(raw, "ORIG_SYS")
    assert reason is None and canon["current_balance"] == Decimal("200000.00")


def test_missing_loan_id_is_a_failure():
    canon, reason = to_canonical({"loan_id": "", "original_principal": "100"}, "S")
    assert canon is None and "loan_id" in reason
