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
