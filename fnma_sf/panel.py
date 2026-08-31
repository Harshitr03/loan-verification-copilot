from __future__ import annotations
from collections import defaultdict
from dataclasses import dataclass

STATIC = ("origination_date", "original_principal", "term_months",
          "maturity_date", "borrower_state", "credit_grade")


@dataclass
class PanelFinding:
    loan_id: str
    reporting_period: object
    kind: str
    field: str
    message: str


def _months(a, b):
    return (b.year - a.year) * 12 + (b.month - a.month)


def check_structure(rows: list[dict]) -> list[PanelFinding]:
    by_loan = defaultdict(list)
    for r in rows:
        by_loan[r["loan_id"]].append(r)
    out: list[PanelFinding] = []
    for lid, group in by_loan.items():
        periods = [r["reporting_period"] for r in group]
        seen = set()
        for p in periods:
            if p in seen:
                out.append(PanelFinding(lid, p, "duplicate_period", "reporting_period",
                                        f"{lid} has duplicate month {p}"))
            seen.add(p)
        ordered = sorted(group, key=lambda r: r["reporting_period"])
        for a, b in zip(ordered, ordered[1:]):
            if _months(a["reporting_period"], b["reporting_period"]) > 1:
                out.append(PanelFinding(lid, b["reporting_period"], "period_gap",
                                        "reporting_period", f"{lid} gap before {b['reporting_period']}"))
            # A leading 0.00 Current Actual UPB means "not reported yet", not a real zero
            # (confirmed: sample loans carry ~6 months of 0.00 before the first real UPB),
            # so only compare consecutive months where BOTH balances are > 0 — otherwise
            # the first real month reads as a spurious increase.
            ab, bb = a["current_balance"], b["current_balance"]
            if ab and bb and ab > 0 and bb > 0 and bb > ab:
                out.append(PanelFinding(lid, b["reporting_period"], "balance_increase",
                                        "current_balance", f"{lid} balance rose at {b['reporting_period']}"))
        first = ordered[0]
        for f in STATIC:
            if any(r.get(f) != first.get(f) for r in ordered):
                out.append(PanelFinding(lid, first["reporting_period"], "static_drift", f,
                                        f"{lid} static field {f} varies across months"))
    return out


from loan_rules import load_rules, validate_dataset, Dataset

PANEL_PROFILE = "sf_performance_panel"


def panel_row_rules():
    return [r for r in load_rules(None) if PANEL_PROFILE in r.profiles]


def validate_panel(rows: list[dict]) -> dict:
    return {
        "structural": check_structure(rows),
        "row_local": validate_dataset(Dataset(rows, [], []), panel_row_rules()),
    }
