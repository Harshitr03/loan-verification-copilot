from datetime import date
from decimal import Decimal
from fnma_sf.parse import iter_rows
from fnma_sf.normalize import normalize_row
from fnma_sf.collapse import collapse_latest


def _r(lid, period, bal):
    return {"loan_id": lid, "reporting_period": period, "current_balance": bal,
            "payment_status": "CURRENT", "row_uid": f"{lid}|x"}


def test_keeps_latest_period_per_loan():
    rows = [_r("L", date(2009, 8, 1), Decimal("90000")),
            _r("L", date(2010, 1, 1), Decimal("50000"))]
    out = collapse_latest(rows)
    assert len(out) == 1
    assert out[0]["current_balance"] == Decimal("50000")   # latest month wins
    assert out[0]["row_uid"] == "L"                          # loan-grain key


def test_sample_collapses_to_eight_loans():
    rows = [normalize_row(r) for r in iter_rows("sf-loan-performance-data-sample.csv")]
    out = collapse_latest(rows)
    assert len(out) == 8
    for loan in out:
        same = [r for r in rows if r["loan_id"] == loan["loan_id"]]
        assert loan["last_updated_at"] == max(r["reporting_period"] for r in same)
