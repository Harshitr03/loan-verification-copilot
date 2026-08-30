from __future__ import annotations
from types import MappingProxyType
from loan_rules.base import Rule, Scope, bundle_from, violation_from
from loan_rules.registry import register
from loan_rules._dates import parse_date

REQUIRED = ("loan_id", "borrower_id", "original_principal", "origination_date")
# Row-local rules apply to BOTH profiles; identity/time rules keep the loan_tape
# default (parent spec §7). `required_fields` and `stale_record` stay loan_tape-only.
BOTH = frozenset({"loan_tape", "sf_performance_panel"})


# --- required_fields -------------------------------------------------------
def _required_check(loan, params):
    for f in params["required"]:
        if loan.get(f) in (None, ""):
            return violation_from(loan, "required_fields", f, loan.get(f), "non-empty",
                                  f"Required field {f} is missing", severity="high")
    return None


def _required_corrupt(loan, rng, params):
    loan = dict(loan)
    f = params["required"][int(rng.integers(len(params["required"])))]
    original = loan.get(f)
    loan[f] = ""
    return loan, bundle_from(loan, "required_fields", f, "", "non-empty",
                             f"Required field {f} is missing", original=original)


register(Rule("required_fields", Scope.ROW, "high",
              MappingProxyType({"required": list(REQUIRED)}),
              "Required field {field} is missing", _required_check, _required_corrupt))


# --- amount rules ----------------------------------------------------------
from decimal import Decimal


def _nonneg_check(loan, params):
    for f in params["fields"]:
        val = loan.get(f)
        if isinstance(val, Decimal) and val < 0:
            return violation_from(loan, "non_negative_amounts", f, val, ">= 0",
                                  f"{f} is negative ({val})", severity="high")
    return None


def _nonneg_corrupt(loan, rng, params):
    loan = dict(loan)
    f = params["fields"][int(rng.integers(len(params["fields"])))]
    original = loan[f]
    loan[f] = -abs(original)
    return loan, bundle_from(loan, "non_negative_amounts", f, loan[f], ">= 0",
                             f"{f} is negative", original=original)


register(Rule("non_negative_amounts", Scope.ROW, "high",
              MappingProxyType({"fields": ["original_principal", "current_balance"]}),
              "{field} is negative", _nonneg_check, _nonneg_corrupt, profiles=BOTH))


def _ble_check(loan, params):
    bal, prin = loan.get("current_balance"), loan.get("original_principal")
    if isinstance(bal, Decimal) and isinstance(prin, Decimal) and bal > prin:
        return violation_from(loan, "balance_le_principal", "current_balance", bal,
                              f"<= {prin}", "current_balance exceeds original_principal",
                              severity="high")
    return None


def _ble_corrupt(loan, rng, params):
    loan = dict(loan)
    original = loan["current_balance"]
    loan["current_balance"] = loan["original_principal"] + Decimal("1000.00")
    return loan, bundle_from(loan, "balance_le_principal", "current_balance",
                             loan["current_balance"], f"<= {loan['original_principal']}",
                             "current_balance exceeds original_principal", original=original)


register(Rule("balance_le_principal", Scope.ROW, "high", MappingProxyType({}),
              "current_balance exceeds original_principal", _ble_check, _ble_corrupt,
              profiles=BOTH))


def _rate_check(loan, params):
    rate = loan.get("interest_rate")
    lo, hi = Decimal(str(params["min"])), Decimal(str(params["max"]))
    if isinstance(rate, Decimal) and not (lo <= rate <= hi):
        return violation_from(loan, "interest_rate_range", "interest_rate", rate,
                              f"{params['min']}-{params['max']}", "interest_rate out of band")
    return None


def _rate_corrupt(loan, rng, params):
    loan = dict(loan)
    original = loan["interest_rate"]
    loan["interest_rate"] = Decimal(str(params["max"])) + Decimal("10.0")
    return loan, bundle_from(loan, "interest_rate_range", "interest_rate",
                             loan["interest_rate"], f"{params['min']}-{params['max']}",
                             "interest_rate out of band", original=original)


register(Rule("interest_rate_range", Scope.ROW, "medium",
              MappingProxyType({"min": 2.0, "max": 36.0}),
              "interest_rate out of band", _rate_check, _rate_corrupt, profiles=BOTH))
