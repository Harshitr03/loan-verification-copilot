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
