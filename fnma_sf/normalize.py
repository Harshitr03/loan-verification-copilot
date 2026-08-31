from __future__ import annotations
from datetime import date
from decimal import Decimal, InvalidOperation

NO_SOURCE = ("borrower_id", "income_band", "document_status")
# Glossary field 27 enum verified against the CRT glossary: P=Purchase, C=Cash-Out
# Refinance, R=Refinance, U=Refinance-Not Specified (U folds into REFI).
_PURPOSE = {"P": "PURCHASE", "C": "CASHOUT", "R": "REFI", "U": "REFI"}
# Glossary field 35 Amortization Type: FRM=Fixed Rate, ARM=Adjustable Rate.
_AMORT = {"FRM": "FIXED", "ARM": "ARM"}


def mmyyyy(s):
    if not s or len(s) != 6 or not s.isdigit():
        return None
    mm, yyyy = int(s[:2]), int(s[2:])
    if not 1 <= mm <= 12:
        return None
    return date(yyyy, mm, 1)


def to_decimal(s):
    if s in (None, ""):
        return None
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def credit_grade(fico):
    if not fico or not fico.isdigit():
        return None
    f = int(fico)
    return "A" if f >= 740 else "B" if f >= 680 else "C" if f >= 620 else "D"


def payment_status(zero_bal, delinq):
    if zero_bal:                       # any zero-balance code -> loan closed
        return "CLOSED"
    if delinq == "00":
        return "CURRENT"
    if delinq.isdigit() and int(delinq) > 0:
        return "DELINQUENT"
    return None                        # "XX"/blank -> unknown


def days_past_due(delinq):
    # FNMA field 40 is a MONTH count ("00","01",…,"XX"); we approximate days as months*30.
    # This is an approximation, not literal days — documented so downstream reads it right.
    return int(delinq) * 30 if delinq.isdigit() else None


def loan_purpose(code):
    return _PURPOSE.get(code) if code else None


def loan_type(code):
    return _AMORT.get(code) if code else None


def _to_int(s):
    return int(s) if s and s.lstrip("-").isdigit() else None


def normalize_row(raw: dict) -> dict:
    period = raw["reporting_period"]
    canon = {
        "loan_id": raw["loan_id"] or None,
        "reporting_period": mmyyyy(period),
        "servicer_name": raw["servicer_name"] or None,
        "interest_rate": to_decimal(raw["interest_rate"]),
        "original_principal": to_decimal(raw["original_principal"]),
        "current_balance": to_decimal(raw["current_balance"]),
        "term_months": _to_int(raw["term_months"]),
        "origination_date": mmyyyy(raw["origination_date"]),
        "maturity_date": mmyyyy(raw["maturity_date"]),
        "borrower_state": raw["borrower_state"] or None,
        "loan_purpose": loan_purpose(raw["loan_purpose"]),
        "loan_type": loan_type(raw["amortization_type"]),
        "credit_grade": credit_grade(raw["credit_score"]),
        "payment_status": payment_status(raw["zero_balance_code"], raw["delinquency"]),
        "days_past_due": days_past_due(raw["delinquency"]),
        "last_payment_date": mmyyyy(raw["last_paid"]),
        "last_updated_at": mmyyyy(period),
        "source_system": "FNMA_SF_LPD",
        "profile": "sf_performance_panel",
        "row_uid": f"{raw['loan_id']}|{period}",
    }
    for f in NO_SOURCE:
        canon[f] = None
    canon["_partial"] = [f for f in NO_SOURCE if canon[f] is None]
    return canon


def is_failed(canon) -> bool:
    return canon["loan_id"] is None or canon["reporting_period"] is None \
        or canon["origination_date"] is None
