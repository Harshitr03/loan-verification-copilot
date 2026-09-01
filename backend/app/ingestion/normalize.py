from decimal import Decimal, InvalidOperation
from loan_rules.rules_row import US_STATES   # reuse the canonical 51-code set
from loan_rules._dates import parse_date      # reuse the shared date parser (no 3rd parser)

VALID_STATES = set(US_STATES)

LOAN_TYPE = {"FIXED": "FIXED", "FXD": "FIXED", "FIXED RATE": "FIXED",
             "FRM": "FIXED", "ARM": "ARM", "ADJUSTABLE": "ARM",
             "ADJUSTABLE RATE": "ARM"}
PURPOSE = {"PURCHASE": "PURCHASE", "P": "PURCHASE", "REFI": "REFI",
           "REFINANCE": "REFI", "R": "REFI", "CASHOUT": "CASHOUT",
           "CASH-OUT": "CASHOUT", "CASH OUT": "CASHOUT", "C": "CASHOUT"}
STATUS = {"CURRENT": "CURRENT", "DELINQUENT": "DELINQUENT", "DELINQ": "DELINQUENT",
          "CLOSED": "CLOSED", "PAID OFF": "CLOSED", "PAID_OFF": "CLOSED"}

NAME_TO_CODE = {
    "Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR",
    "California": "CA", "Colorado": "CO", "Connecticut": "CT", "Delaware": "DE",
    "Florida": "FL", "Georgia": "GA", "Hawaii": "HI", "Idaho": "ID",
    "Illinois": "IL", "Indiana": "IN", "Iowa": "IA", "Kansas": "KS",
    "Kentucky": "KY", "Louisiana": "LA", "Maine": "ME", "Maryland": "MD",
    "Massachusetts": "MA", "Michigan": "MI", "Minnesota": "MN", "Mississippi": "MS",
    "Missouri": "MO", "Montana": "MT", "Nebraska": "NE", "Nevada": "NV",
    "New Hampshire": "NH", "New Jersey": "NJ", "New Mexico": "NM", "New York": "NY",
    "North Carolina": "NC", "North Dakota": "ND", "Ohio": "OH", "Oklahoma": "OK",
    "Oregon": "OR", "Pennsylvania": "PA", "Rhode Island": "RI", "South Carolina": "SC",
    "South Dakota": "SD", "Tennessee": "TN", "Texas": "TX", "Utah": "UT",
    "Vermont": "VT", "Virginia": "VA", "Washington": "WA", "West Virginia": "WV",
    "Wisconsin": "WI", "Wyoming": "WY", "District Of Columbia": "DC",
}

def _clean(s):
    return (s or "").strip()


def _money(s):
    s = _clean(s).replace("$", "").replace(",", "").replace("%", "")
    if not s:
        return None
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def _date(s):
    # Lenient, reusing loan_rules.parse_date: parseable -> date; empty -> None;
    # unparseable -> the raw string kept verbatim so the `valid_dates` rule (not
    # normalization) flags it at validation.
    s = _clean(s)
    if not s:
        return None
    d = parse_date(s)
    return d if d is not None else s


def _int(s):
    s = _clean(s)
    return int(s) if s else None


def _enum(val, table):
    v = _clean(val)
    return table.get(v.upper()) if v else None


def _state(s):
    s = _clean(s)
    if not s:
        return None
    if s.upper() in VALID_STATES:
        return s.upper()
    return NAME_TO_CODE.get(s.title())


_DATE_FIELDS = ("origination_date", "maturity_date", "last_payment_date", "last_updated_at")


def to_storable(canon: dict) -> dict:
    """Project a lenient canonical dict onto values the typed Loan model accepts:
    an unparseable date is kept as a raw string for validation but must be None
    in the typed store."""
    d = dict(canon)
    for f in _DATE_FIELDS:
        if isinstance(d.get(f), str):
            d[f] = None
    return d


def to_canonical(raw: dict, source_system: str) -> tuple[dict | None, str | None]:
    # Only a missing loan_id (the primary key) fails a row -> failed import.
    # Every other bad value is kept (typed if parseable, raw string if not) so the
    # 15 rules flag it at validation, matching the generator's loan-dict semantics.
    try:
        lid = _clean(raw.get("loan_id"))
        if not lid:
            return None, "missing loan_id"
        canon = {
            "loan_id": lid,
            "borrower_id": _clean(raw.get("borrower_id")) or None,
            "loan_type": _enum(raw.get("loan_type"), LOAN_TYPE),
            "origination_date": _date(raw.get("origination_date")),
            "maturity_date": _date(raw.get("maturity_date")),
            "original_principal": _money(raw.get("original_principal")),
            "current_balance": _money(raw.get("current_balance")),
            "interest_rate": _money(raw.get("interest_rate")),
            "term_months": _int(raw.get("term_months")),
            "borrower_state": _state(raw.get("borrower_state")),
            "loan_purpose": _enum(raw.get("loan_purpose"), PURPOSE),
            "credit_grade": _clean(raw.get("credit_grade")) or None,
            "employment_length": _clean(raw.get("employment_length")) or None,
            "income_band": _clean(raw.get("income_band")) or None,
            "payment_status": _enum(raw.get("payment_status"), STATUS),
            "days_past_due": _int(raw.get("days_past_due")),
            "servicer_name": _clean(raw.get("servicer_name")) or None,
            "last_payment_date": _date(raw.get("last_payment_date")),
            "last_updated_at": _date(raw.get("last_updated_at")),
            "document_status": _clean(raw.get("document_status")) or None,
            "source_system": source_system,
        }
        return canon, None
    except (ValueError, InvalidOperation) as e:
        return None, str(e)
