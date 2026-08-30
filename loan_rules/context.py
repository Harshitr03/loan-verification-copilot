from __future__ import annotations
from collections import Counter
from loan_rules.base import Dataset, Scope, Violation


def build_context(ds: Dataset) -> dict:
    return {
        "loan_id_counts": Counter(l.get("loan_id") for l in ds.loans),
        "combo_counts": Counter(
            (l.get("borrower_id"), str(l.get("original_principal")), str(l.get("origination_date")))
            for l in ds.loans),
        "borrower_counts": Counter(l.get("borrower_id") for l in ds.loans),
        "servicer_by_loan": {s["loan_id"]: s for s in ds.servicer_updates},
        "manifest_ids": {m["loan_id"] for m in ds.manifest},
    }


def validate_dataset(ds: Dataset, rules) -> list[Violation]:
    ctx = build_context(ds)
    out: list[Violation] = []
    for rule in rules:
        if rule.scope == Scope.ROW:
            for loan in ds.loans:
                v = rule.check(loan, rule.params)
                if v is not None:
                    v.severity = rule.severity
                    out.append(v)
        else:
            for v in rule.check(ds, ctx, rule.params):
                v.severity = rule.severity
                out.append(v)
    return out
