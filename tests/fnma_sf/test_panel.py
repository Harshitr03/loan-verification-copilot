from datetime import date
from decimal import Decimal
from fnma_sf.panel import check_structure


def _row(lid, period, **over):
    r = {"loan_id": lid, "reporting_period": period, "origination_date": date(2009, 8, 1),
         "original_principal": Decimal("100000"), "term_months": 240,
         "maturity_date": date(2029, 9, 1), "borrower_state": "OH", "credit_grade": "B",
         "current_balance": Decimal("90000")}
    r.update(over)
    return r


def test_clean_two_months_no_findings():
    rows = [_row("L", date(2009, 8, 1)), _row("L", date(2009, 9, 1), current_balance=Decimal("89000"))]
    assert check_structure(rows) == []


def test_duplicate_period_flagged():
    rows = [_row("L", date(2009, 8, 1)), _row("L", date(2009, 8, 1))]
    assert any(f.kind == "duplicate_period" for f in check_structure(rows))


def test_gap_in_months_flagged():
    rows = [_row("L", date(2009, 8, 1)), _row("L", date(2009, 11, 1))]
    assert any(f.kind == "period_gap" for f in check_structure(rows))


def test_static_field_drift_flagged():
    rows = [_row("L", date(2009, 8, 1)), _row("L", date(2009, 9, 1), original_principal=Decimal("999"))]
    assert any(f.kind == "static_drift" and f.field == "original_principal"
               for f in check_structure(rows))


def test_balance_increase_flagged():
    rows = [_row("L", date(2009, 8, 1), current_balance=Decimal("90000")),
            _row("L", date(2009, 9, 1), current_balance=Decimal("95000"))]
    assert any(f.kind == "balance_increase" for f in check_structure(rows))


def test_leading_zero_upb_not_flagged_as_increase():
    # A leading 0.00 UPB is "not reported yet" (confirmed in the sample), not a real
    # zero — the jump to the first real balance must NOT read as an increase.
    rows = [_row("L", date(2009, 8, 1), current_balance=Decimal("0.00")),
            _row("L", date(2009, 9, 1), current_balance=Decimal("54350.98"))]
    assert not any(f.kind == "balance_increase" for f in check_structure(rows))


from fnma_sf.panel import panel_row_rules, validate_panel


def test_subset_excludes_identity_and_time_rules():
    ids = {r.id for r in panel_row_rules()}
    assert "duplicate_loan_id" not in ids and "stale_record" not in ids
    assert "required_fields" not in ids and "document_status_present" not in ids
    assert {"valid_dates", "non_negative_amounts", "interest_rate_range",
            "balance_le_principal", "closed_with_balance", "maturity_after_origination",
            "payment_status_vs_dpd", "valid_state_code"} <= ids


def test_row_local_rule_flags_bad_rate_on_a_panel_row():
    row = {"row_uid": "L|082009", "loan_id": "L", "reporting_period": date(2009, 8, 1),
           "origination_date": date(2009, 8, 1), "maturity_date": date(2029, 9, 1),
           "original_principal": Decimal("100000"), "current_balance": Decimal("90000"),
           "interest_rate": Decimal("99.0"), "borrower_state": "OH",
           "payment_status": "CURRENT", "days_past_due": 0}
    res = validate_panel([row])
    assert any(v.rule_id == "interest_rate_range" for v in res["row_local"])
