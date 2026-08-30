from __future__ import annotations
import csv
import json
from datetime import date
from decimal import Decimal
import bcrypt

CANONICAL_COLUMNS = [
    "loan_id", "borrower_id", "loan_type", "origination_date", "maturity_date",
    "original_principal", "current_balance", "interest_rate", "term_months",
    "borrower_state", "loan_purpose", "credit_grade", "employment_length",
    "income_band", "payment_status", "days_past_due", "servicer_name",
    "last_payment_date", "last_updated_at", "document_status", "source_system",
]
_GT_COLUMNS = ["row_uid", "loan_id", "rule_id", "field", "observed_value", "expected",
               "sibling_value", "original_value", "message"]
_SAMPLE_COLUMNS = ["loan_id", "rule_id", "field", "observed_value", "expected",
                   "sibling_value", "message"]


def format_value(v):
    if v is None:
        return ""
    if isinstance(v, Decimal):
        return str(v.quantize(Decimal("0.01")))
    if isinstance(v, date):
        return v.isoformat()
    return str(v)


def _write(path, columns, rows):
    with open(path, "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(columns)
        for r in rows:
            w.writerow([format_value(r.get(c) if isinstance(r, dict) else getattr(r, c, None))
                        for c in columns])


def write_loans_csv(path, loans):
    _write(path, CANONICAL_COLUMNS, loans)


def write_rows_csv(path, rows, columns):
    _write(path, columns, rows)


def write_ground_truth_csv(path, bundles):
    _write(path, _GT_COLUMNS, bundles)


def write_sample_csv(path, bundles):
    _write(path, _SAMPLE_COLUMNS, bundles)


def write_users_json(path, users):
    out = [{"username": u["username"], "role": u["role"], "display_name": u["display_name"],
            "password_hash": bcrypt.hashpw(u["password"].encode(), bcrypt.gensalt()).decode()}
           for u in users]
    with open(path, "w") as f:
        json.dump(out, f, sort_keys=True, indent=2)
