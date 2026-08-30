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
    # strictly negative even when original is 0.00 (CLOSED loans carry a zero
    # current_balance, and -abs(0.00) == -0.00 is not < 0, so the check misses it)
    loan[f] = -(abs(original) + Decimal("1000.00"))
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


# --- date rules ------------------------------------------------------------
from datetime import timedelta


def _valid_dates_check(loan, params):
    for f in params["fields"]:
        val = loan.get(f)
        if val in (None, ""):
            continue
        if parse_date(val) is None:
            return violation_from(loan, "valid_dates", f, val, "parseable date",
                                  f"{f} is not a valid date", severity="high")
    return None


def _valid_dates_corrupt(loan, rng, params):
    loan = dict(loan)
    f = params["fields"][int(rng.integers(len(params["fields"])))]
    original = loan[f]
    loan[f] = "13/40/2020"
    return loan, bundle_from(loan, "valid_dates", f, loan[f], "parseable date",
                             f"{f} is not a valid date", original=original)


register(Rule("valid_dates", Scope.ROW, "high",
              MappingProxyType({"fields": ["origination_date", "maturity_date",
                                           "last_payment_date", "last_updated_at"]}),
              "{field} is not a valid date", _valid_dates_check, _valid_dates_corrupt,
              profiles=BOTH))


def _mao_check(loan, params):
    o, m = parse_date(loan.get("origination_date")), parse_date(loan.get("maturity_date"))
    if o and m and m < o:
        return violation_from(loan, "maturity_after_origination", "maturity_date", m,
                              f">= {o}", "maturity_date precedes origination_date", severity="high")
    return None


def _mao_corrupt(loan, rng, params):
    loan = dict(loan)
    o = parse_date(loan["origination_date"])
    original = loan["maturity_date"]
    loan["maturity_date"] = o - timedelta(days=365)
    return loan, bundle_from(loan, "maturity_after_origination", "maturity_date",
                             loan["maturity_date"], f">= {o}",
                             "maturity_date precedes origination_date", original=original)


register(Rule("maturity_after_origination", Scope.ROW, "high", MappingProxyType({}),
              "maturity_date precedes origination_date", _mao_check, _mao_corrupt,
              profiles=BOTH))


def _stale_check(loan, params):
    as_of, lu = parse_date(params["as_of"]), parse_date(loan.get("last_updated_at"))
    if lu and (as_of - lu).days > params["max_age_days"]:
        return violation_from(loan, "stale_record", "last_updated_at", lu,
                              f"within {params['max_age_days']}d of {as_of}",
                              "record is stale", severity="low")
    return None


def _stale_corrupt(loan, rng, params):
    loan = dict(loan)
    as_of = parse_date(params["as_of"])
    original = loan["last_updated_at"]
    loan["last_updated_at"] = as_of - timedelta(days=params["max_age_days"] + 400)
    return loan, bundle_from(loan, "stale_record", "last_updated_at",
                             loan["last_updated_at"], f"within {params['max_age_days']}d",
                             "record is stale", original=original)


register(Rule("stale_record", Scope.ROW, "low",
              MappingProxyType({"as_of": "2024-07-01", "max_age_days": 180}),
              "record is stale", _stale_check, _stale_corrupt))


# --- categorical rules -----------------------------------------------------
US_STATES = [
    "AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","ID","IL","IN","IA",
    "KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ",
    "NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT","VT",
    "VA","WA","WV","WI","WY","DC",
]


def _state_check(loan, params):
    st = loan.get("borrower_state")
    if st not in params["states"]:
        return violation_from(loan, "valid_state_code", "borrower_state", st,
                              "valid US code", "borrower_state is not a valid US code")
    return None


def _state_corrupt(loan, rng, params):
    loan = dict(loan)
    original = loan["borrower_state"]
    loan["borrower_state"] = "ZZ"
    return loan, bundle_from(loan, "valid_state_code", "borrower_state", "ZZ",
                             "valid US code", "borrower_state is not a valid US code",
                             original=original)


register(Rule("valid_state_code", Scope.ROW, "medium",
              MappingProxyType({"states": US_STATES}),
              "borrower_state is not a valid US code", _state_check, _state_corrupt,
              profiles=BOTH))


def _psd_check(loan, params):
    status, dpd = loan.get("payment_status"), loan.get("days_past_due")
    if not isinstance(dpd, int):
        return None
    if status == "CURRENT" and dpd > 0:
        return violation_from(loan, "payment_status_vs_dpd", "days_past_due", dpd,
                              "0 for CURRENT", "CURRENT loan has positive days_past_due")
    if status == "DELINQUENT" and dpd == 0:
        return violation_from(loan, "payment_status_vs_dpd", "days_past_due", dpd,
                              ">0 for DELINQUENT", "DELINQUENT loan has days_past_due=0")
    return None


def _psd_corrupt(loan, rng, params):
    loan = dict(loan)
    original = loan["days_past_due"]
    loan["payment_status"] = "CURRENT"
    loan["days_past_due"] = 90
    return loan, bundle_from(loan, "payment_status_vs_dpd", "days_past_due", 90,
                             "0 for CURRENT", "CURRENT loan has positive days_past_due",
                             original=original)


register(Rule("payment_status_vs_dpd", Scope.ROW, "medium", MappingProxyType({}),
              "payment_status inconsistent with days_past_due", _psd_check, _psd_corrupt,
              profiles=BOTH))


def _cwb_check(loan, params):
    bal = loan.get("current_balance")
    if loan.get("payment_status") == "CLOSED" and isinstance(bal, Decimal) and bal > 0:
        return violation_from(loan, "closed_with_balance", "current_balance", bal,
                              "0 for CLOSED", "CLOSED loan has positive balance", severity="high")
    return None


def _cwb_corrupt(loan, rng, params):
    loan = dict(loan)
    original = loan["current_balance"]
    loan["payment_status"] = "CLOSED"
    loan["current_balance"] = Decimal("5000.00")
    return loan, bundle_from(loan, "closed_with_balance", "current_balance",
                             Decimal("5000.00"), "0 for CLOSED",
                             "CLOSED loan has positive balance", original=original)


register(Rule("closed_with_balance", Scope.ROW, "high", MappingProxyType({}),
              "CLOSED loan has positive balance", _cwb_check, _cwb_corrupt, profiles=BOTH))


# --- corrupt field footprints ----------------------------------------------
# Fields each ROW `corrupt` reads or writes. The generator uses these to avoid
# co-locating two defects that touch a shared field on one loan — which would
# otherwise crash (reading a field a prior defect blanked) or mask each other
# (a later write healing an earlier defect), breaking the superset oracle.
# MUST be kept in sync with the corrupts above (guarded by a test).
ROW_FOOTPRINTS = {
    "required_fields": frozenset(REQUIRED),  # may blank any required field
    "valid_dates": frozenset({"origination_date", "maturity_date",
                              "last_payment_date", "last_updated_at"}),
    "maturity_after_origination": frozenset({"origination_date", "maturity_date"}),
    "non_negative_amounts": frozenset({"original_principal", "current_balance"}),
    "balance_le_principal": frozenset({"original_principal", "current_balance"}),
    "interest_rate_range": frozenset({"interest_rate"}),
    "payment_status_vs_dpd": frozenset({"payment_status", "days_past_due"}),
    "closed_with_balance": frozenset({"payment_status", "current_balance"}),
    "valid_state_code": frozenset({"borrower_state"}),
    "stale_record": frozenset({"last_updated_at"}),
}
