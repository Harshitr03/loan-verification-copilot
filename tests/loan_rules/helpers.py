from datetime import date
from decimal import Decimal


def make_clean_loan(i=1, **overrides):
    loan = {
        "row_uid": f"U{i:05d}", "loan_id": f"LN{i:05d}", "borrower_id": f"BR{i:05d}",
        "loan_type": "FIXED", "origination_date": date(2020, 1, 15),
        "maturity_date": date(2050, 1, 15), "original_principal": Decimal("250000.00"),
        "current_balance": Decimal("200000.00"), "interest_rate": Decimal("5.25"),
        "term_months": 360, "borrower_state": "CA", "loan_purpose": "PURCHASE",
        "credit_grade": "A", "employment_length": 10, "income_band": "100K-150K",
        "payment_status": "CURRENT", "days_past_due": 0, "servicer_name": "Acme Servicing",
        "last_payment_date": date(2024, 6, 1), "last_updated_at": date(2024, 6, 15),
        "document_status": "COMPLETE", "source_system": "ORIG_SYS",
    }
    loan.update(overrides)
    return loan


from loan_rules.base import Dataset


def make_clean_dataset(n=6):
    loans = [make_clean_loan(i) for i in range(n)]
    servicer = [{"loan_id": l["loan_id"], "current_balance": l["current_balance"],
                 "interest_rate": l["interest_rate"], "payment_status": l["payment_status"]}
                for l in loans[: max(1, n // 2)]]
    manifest = [{"loan_id": l["loan_id"], "document_status": "COMPLETE"} for l in loans]
    return Dataset(loans=loans, servicer_updates=servicer, manifest=manifest)
