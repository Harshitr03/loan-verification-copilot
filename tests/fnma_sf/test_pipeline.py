from fnma_sf.parse import iter_rows
from fnma_sf.normalize import normalize_row
from fnma_sf.pipeline import ingest_panel


def test_end_to_end_on_sample_no_null_field_floods():
    rows = [normalize_row(r) for r in iter_rows("sf-loan-performance-data-sample.csv")]
    res = ingest_panel(rows)
    assert len(res["loan_tape"]) == 8                 # collapsed
    assert res["failed"] == []                        # sample rows all parse
    assert isinstance(res["loan_exceptions"], list)   # ran; no oracle on real data
    flagged = {v.rule_id for v in res["loan_exceptions"]}
    # the four null-field artifacts must NOT appear (borrower_id / document_status absent):
    #   - required_fields, document_status_present are Pass-3-skipped for this source
    #   - suspicious_borrower_repeat, duplicate_borrower_combo are null-guarded in loan_rules
    assert flagged.isdisjoint({"required_fields", "document_status_present",
                               "suspicious_borrower_repeat", "duplicate_borrower_combo"})
    # (stale_record MAY flag all 8 — the sample is 2009–2020 vintage vs the rule's
    #  as_of; that's an honest finding, not a null-field artifact, so it's allowed.)


def test_failed_rows_are_separated_not_crashing():
    rows = [normalize_row({"loan_id": "", "reporting_period": "082009",
                           "servicer_name": "", "interest_rate": "", "original_principal": "",
                           "current_balance": "", "term_months": "", "origination_date": "082009",
                           "maturity_date": "", "borrower_state": "", "loan_purpose": "",
                           "credit_score": "", "zero_balance_code": "", "delinquency": "00",
                           "last_paid": "", "amortization_type": ""})]
    res = ingest_panel(rows)
    assert len(res["failed"]) == 1 and res["loan_tape"] == []


import csv
from fnma_sf.pipeline import build_demo_tape
from data._serialize import CANONICAL_COLUMNS


def test_build_demo_tape_streams_and_collapses(tmp_path):
    out = tmp_path / "loan_tape.csv"
    n = build_demo_tape("sf-loan-performance-data-sample.csv", str(out), n_loans=8)
    assert n == 8
    with open(out) as f:
        reader = csv.reader(f)
        header = next(reader)
        body = list(reader)
    assert header == CANONICAL_COLUMNS           # canonical 21 cols, no row_uid leaked
    assert len(body) == 8                        # collapsed to 8 loans


def test_build_demo_tape_caps_distinct_loans(tmp_path):
    out = tmp_path / "t.csv"
    assert build_demo_tape("sf-loan-performance-data-sample.csv", str(out), n_loans=3) == 3
