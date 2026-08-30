from datetime import date
from decimal import Decimal
from loan_rules.base import Bundle
from data._serialize import (format_value, write_loans_csv, write_sample_csv,
                             CANONICAL_COLUMNS)
from tests.loan_rules.helpers import make_clean_loan


def test_format_value_stable():
    assert format_value(Decimal("5")) == "5.00"
    assert format_value(date(2020, 1, 2)) == "2020-01-02"
    assert format_value(None) == ""


def test_loans_csv_header_is_canonical_only(tmp_path):
    p = tmp_path / "loan_tape.csv"
    write_loans_csv(str(p), [make_clean_loan()])
    header = p.read_text().splitlines()[0]
    assert header == ",".join(CANONICAL_COLUMNS)      # no row_uid leaked into the tape


def test_loans_csv_byte_identical(tmp_path):
    loans = [make_clean_loan(i) for i in range(20)]
    a, b = tmp_path / "a.csv", tmp_path / "b.csv"
    write_loans_csv(str(a), loans); write_loans_csv(str(b), loans)
    assert a.read_bytes() == b.read_bytes()


def test_sample_excludes_oracle_columns(tmp_path):
    p = tmp_path / "sample.csv"
    write_sample_csv(str(p), [Bundle("U1", "LN1", "r", "f", 1, 2, "m", original_value=0)])
    header = p.read_text().splitlines()[0]
    assert "row_uid" not in header and "original_value" not in header
