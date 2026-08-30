from types import MappingProxyType
import dataclasses
import pytest
from loan_rules.base import Scope, Rule, Bundle, Violation, bundle_from, violation_from


def _c(loan, params): return None
def _x(loan, rng, params): return loan, None


def make_rule(rid="r"):
    return Rule(id=rid, scope=Scope.ROW, severity="low",
                params=MappingProxyType({"a": 1}), message_tmpl="{field}",
                check=_c, corrupt=_x)


def test_rule_is_frozen():
    with pytest.raises(dataclasses.FrozenInstanceError):
        make_rule().id = "x"


def test_rule_is_hashable_and_eq_by_id():
    assert {make_rule(), make_rule()} == {make_rule()}     # hashable; equal by id
    assert make_rule("a") != make_rule("b")


def test_params_is_readonly_mapping():
    with pytest.raises(TypeError):
        make_rule().params["a"] = 99


def test_factories_read_row_uid_and_loan_id():
    loan = {"row_uid": "U1", "loan_id": "LN1"}
    b = bundle_from(loan, "r", "f", 1, 2, "m", original=0)
    v = violation_from(loan, "r", "f", 1, 2, "m", severity="high")
    assert (b.row_uid, b.loan_id, b.original_value) == ("U1", "LN1", 0)
    assert (v.row_uid, v.loan_id, v.severity) == ("U1", "LN1", "high")


def test_rule_profiles_default_is_loan_tape():
    assert make_rule().profiles == frozenset({"loan_tape"})
