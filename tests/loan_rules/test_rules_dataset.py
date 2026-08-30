import numpy as np
import pytest
from loan_rules.base import Scope
from loan_rules import registry
from loan_rules.context import build_context
import loan_rules.rules_dataset  # noqa: F401
from tests.loan_rules.helpers import make_clean_dataset

DATASET_RULES = [r for r in registry.ALL_RULES if r.scope == Scope.DATASET]


def _rule(rid):
    return next(r for r in DATASET_RULES if r.id == rid)


@pytest.mark.parametrize("rule", DATASET_RULES, ids=lambda r: r.id)
def test_dataset_round_trip(rule):
    rng = np.random.default_rng(0)
    clean = make_clean_dataset()
    assert rule.check(clean, build_context(clean), rule.params) == [], "clean must pass"
    ds2, bundles = rule.corrupt(make_clean_dataset(), rng, rule.params)
    flagged = {v.row_uid for v in rule.check(ds2, build_context(ds2), rule.params)}
    implicated = {b.row_uid for b in bundles}
    assert implicated and implicated <= flagged, f"{rule.id}: implicated not all flagged"


def test_duplicate_loan_id_flags_two_distinct_rows():
    rng = np.random.default_rng(1)
    _, bundles = _rule("duplicate_loan_id").corrupt(make_clean_dataset(), rng, {})
    assert len({b.row_uid for b in bundles}) == 2   # keyed on row_uid, not loan_id
