import numpy as np
import pytest
from loan_rules.base import Scope
from loan_rules import registry
import loan_rules.rules_row  # noqa: F401  (registers rules)
from tests.loan_rules.helpers import make_clean_loan

ROW_RULES = [r for r in registry.ALL_RULES if r.scope == Scope.ROW]


def _rule(rid):
    return next(r for r in ROW_RULES if r.id == rid)


@pytest.mark.parametrize("rule", ROW_RULES, ids=lambda r: r.id)
def test_row_round_trip(rule):
    rng = np.random.default_rng(0)
    clean = make_clean_loan()
    assert rule.check(clean, rule.params) is None, "clean must pass"
    corrupted, bundle = rule.corrupt(make_clean_loan(), rng, rule.params)
    v = rule.check(corrupted, rule.params)
    assert v is not None, f"{rule.id}: injected defect not detected"
    assert v.field == bundle.field
    assert bundle.row_uid == corrupted["row_uid"]


def test_required_fields_edge_blank_borrower():
    assert _rule("required_fields").check(make_clean_loan(borrower_id=""), _rule("required_fields").params) is not None


from decimal import Decimal


def test_non_negative_amounts_edge():
    r = _rule("non_negative_amounts")
    assert r.check(make_clean_loan(current_balance=Decimal("-1.00")), r.params) is not None


def test_non_negative_corrupt_detects_zero_balance():
    # regression: a CLOSED loan's current_balance is 0.00; the corrupt must still
    # produce a strictly-negative value the check flags (not -0.00).
    import numpy as np
    r = _rule("non_negative_amounts")
    loan = make_clean_loan(payment_status="CLOSED", current_balance=Decimal("0.00"))
    # force it to target current_balance (fields = [original_principal, current_balance])
    params = dict(r.params); params["fields"] = ["current_balance"]
    corrupted, bundle = r.corrupt(loan, np.random.default_rng(0), params)
    assert r.check(corrupted, r.params) is not None


def test_balance_le_principal_edge():
    r = _rule("balance_le_principal")
    assert r.check(make_clean_loan(current_balance=Decimal("300000.00"),
                                   original_principal=Decimal("250000.00")), r.params) is not None


def test_interest_rate_range_edge():
    r = _rule("interest_rate_range")
    assert r.check(make_clean_loan(interest_rate=Decimal("45.0")), r.params) is not None
    assert r.check(make_clean_loan(interest_rate=Decimal("5.0")), r.params) is None


from datetime import date


def test_valid_dates_edge():
    r = _rule("valid_dates")
    assert r.check(make_clean_loan(maturity_date="13/40/2020"), r.params) is not None


def test_maturity_after_origination_edge():
    r = _rule("maturity_after_origination")
    assert r.check(make_clean_loan(origination_date=date(2050, 1, 1),
                                   maturity_date=date(2020, 1, 1)), r.params) is not None


def test_stale_record_edge():
    r = _rule("stale_record")
    assert r.check(make_clean_loan(last_updated_at=date(2000, 1, 1)), r.params) is not None


def test_valid_state_code_edge():
    r = _rule("valid_state_code")
    assert r.check(make_clean_loan(borrower_state="ZZ"), r.params) is not None


def test_payment_status_vs_dpd_edge():
    r = _rule("payment_status_vs_dpd")
    assert r.check(make_clean_loan(payment_status="CURRENT", days_past_due=90), r.params) is not None


def test_closed_with_balance_edge():
    r = _rule("closed_with_balance")
    assert r.check(make_clean_loan(payment_status="CLOSED",
                                   current_balance=Decimal("5000.00")), r.params) is not None


def test_every_row_rule_has_a_footprint():
    from loan_rules.rules_row import ROW_FOOTPRINTS
    assert {r.id for r in ROW_RULES} == set(ROW_FOOTPRINTS), \
        "ROW_FOOTPRINTS must list exactly the ROW rules (kept in sync with the corrupts)"
