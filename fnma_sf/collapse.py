from __future__ import annotations
from collections import defaultdict

_DROP = ("reporting_period", "_partial", "profile")


def collapse_latest(rows: list[dict]) -> list[dict]:
    by_loan = defaultdict(list)
    for r in rows:
        by_loan[r["loan_id"]].append(r)
    out = []
    for lid in sorted(by_loan):
        latest = max(by_loan[lid], key=lambda r: r["reporting_period"])
        loan = {k: v for k, v in latest.items() if k not in _DROP}
        loan["row_uid"] = lid                    # loan-grain unique key
        out.append(loan)
    return out
