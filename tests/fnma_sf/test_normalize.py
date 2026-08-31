from datetime import date
from decimal import Decimal
from fnma_sf.parse import parse_line
from fnma_sf.normalize import (mmyyyy, credit_grade, payment_status, days_past_due,
                               loan_purpose, loan_type, normalize_row, is_failed)


def test_mmyyyy_month_precision():
    assert mmyyyy("082009") == date(2009, 8, 1)
    assert mmyyyy("") is None and mmyyyy("13/40") is None


def test_credit_grade_bands():
    assert (credit_grade("740"), credit_grade("714"), credit_grade("650"),
            credit_grade("600"), credit_grade("")) == ("A", "B", "C", "D", None)


def test_payment_status_and_dpd():
    assert payment_status("01", "00") == "CLOSED"        # zero-bal present -> closed
    assert payment_status("", "00") == "CURRENT"
    assert payment_status("", "03") == "DELINQUENT"
    assert payment_status("", "XX") is None
    assert days_past_due("03") == 90 and days_past_due("00") == 0 and days_past_due("XX") is None


def test_loan_purpose_enum_incl_U():
    assert [loan_purpose(c) for c in ("P", "C", "R", "U", "")] == \
           ["PURCHASE", "CASHOUT", "REFI", "REFI", None]


def test_loan_type_from_amortization():
    assert [loan_type(c) for c in ("FRM", "ARM", "")] == ["FIXED", "ARM", None]


def test_normalize_real_first_row_maps_and_flags_nulls():
    with open("sf-loan-performance-data-sample.csv") as f:
        canon = normalize_row(parse_line(next(f)))
    assert canon["loan_id"] == "100023020488"
    assert canon["interest_rate"] == Decimal("5.375")
    assert canon["origination_date"] == date(2009, 8, 1)
    assert canon["maturity_date"] == date(2029, 9, 1)
    assert canon["borrower_state"] == "OH"
    assert canon["credit_grade"] == "B"
    assert canon["loan_purpose"] == "CASHOUT"
    assert canon["loan_type"] == "FIXED"                 # from Amortization Type FRM (field 35)
    assert canon["original_principal"] == Decimal("55000.00")
    assert canon["row_uid"] == "100023020488|082009"
    assert canon["source_system"] == "FNMA_SF_LPD"
    # no-source fields are null and surfaced as partial, not crashes
    assert canon["borrower_id"] is None and canon["document_status"] is None
    assert set(canon["_partial"]) >= {"borrower_id", "income_band", "document_status"}
    assert is_failed(canon) is False
