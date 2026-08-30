from __future__ import annotations
from datetime import date, timedelta
from decimal import Decimal
import numpy as np
from faker import Faker
from loan_rules.base import Dataset

CREDIT_GRADES = ["A", "B", "C", "D"]
RATE_BAND = {"A": (4.0, 6.0), "B": (6.0, 8.0), "C": (8.0, 11.0), "D": (11.0, 15.0)}
LOAN_TYPES = ["FIXED", "ARM"]
PURPOSES = ["PURCHASE", "REFI", "CASHOUT"]
INCOME_BANDS = ["<50K", "50K-100K", "100K-150K", ">150K"]
STATUSES = ["CURRENT", "DELINQUENT", "CLOSED"]
STATES = ["CA", "TX", "NY", "FL", "WA", "IL", "PA", "OH", "GA", "NC"]
SERVICERS = ["Acme Servicing", "BlueRiver Loan Servicing", "Cardinal Mortgage Co"]
AS_OF = date(2024, 7, 1)


def _money(rng, lo, hi):
    return Decimal(str(round(float(rng.uniform(lo, hi)), 2))).quantize(Decimal("0.01"))


def _pick(rng, seq):
    return seq[int(rng.integers(len(seq)))]


def build_clean_loan(rng, i):
    grade = _pick(rng, CREDIT_GRADES)
    lo, hi = RATE_BAND[grade]
    principal = _money(rng, 50_000, 500_000)
    status = _pick(rng, STATUSES)
    orig = date(2015, 1, 1) + timedelta(days=int(rng.integers(0, 2500)))
    term = int(rng.choice([120, 180, 240, 360]))
    if status == "CLOSED":
        balance, dpd = Decimal("0.00"), 0
    else:
        balance = (principal * Decimal(str(round(float(rng.uniform(0.3, 0.95)), 2)))).quantize(Decimal("0.01"))
        dpd = 0 if status == "CURRENT" else int(rng.integers(30, 180))
    return {
        "row_uid": f"U{i:05d}", "loan_id": f"LN{i:05d}", "borrower_id": f"BR{i:05d}",
        "loan_type": _pick(rng, LOAN_TYPES), "origination_date": orig,
        "maturity_date": orig + timedelta(days=term * 30),
        "original_principal": principal, "current_balance": balance,
        "interest_rate": _money(rng, lo, hi), "term_months": term,
        "borrower_state": _pick(rng, STATES), "loan_purpose": _pick(rng, PURPOSES),
        "credit_grade": grade, "employment_length": int(rng.integers(0, 35)),
        "income_band": _pick(rng, INCOME_BANDS), "payment_status": status,
        "days_past_due": dpd, "servicer_name": _pick(rng, SERVICERS),
        "last_payment_date": AS_OF - timedelta(days=int(rng.integers(1, 60))),
        "last_updated_at": AS_OF - timedelta(days=int(rng.integers(1, 120))),
        "document_status": "COMPLETE", "source_system": "ORIG_SYS",
    }


def build_clean_dataset(n, seed):
    rng = np.random.default_rng(seed)
    Faker().seed_instance(seed)                 # seed Faker even if unused, for future name fields
    loans = [build_clean_loan(rng, i) for i in range(n)]
    servicer = [{"loan_id": l["loan_id"], "current_balance": l["current_balance"],
                 "interest_rate": l["interest_rate"], "payment_status": l["payment_status"]}
                for l in loans if rng.random() < 0.40]
    manifest = [{"loan_id": l["loan_id"], "document_status": l["document_status"]} for l in loans]
    return Dataset(loans=loans, servicer_updates=servicer, manifest=manifest)
