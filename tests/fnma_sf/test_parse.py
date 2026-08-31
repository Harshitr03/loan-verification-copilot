from fnma_sf.parse import parse_line, iter_rows

SAMPLE = "sf-loan-performance-data-sample.csv"


def test_leading_pipe_indexing_on_real_first_row():
    with open(SAMPLE) as f:
        rec = parse_line(next(f))
    # These exact values come from the real sample's first line; a naive parts[N]
    # (ignoring the leading pipe) would shift every field and fail here.
    assert rec["loan_id"] == "100023020488"
    assert rec["reporting_period"] == "082009"
    assert rec["interest_rate"] == "5.375"
    assert rec["original_principal"] == "55000.00"
    assert rec["term_months"] == "240"
    assert rec["origination_date"] == "082009"
    assert rec["maturity_date"] == "092029"
    assert rec["borrower_state"] == "OH"
    assert rec["loan_purpose"] == "C"
    assert rec["credit_score"] == "714"


def test_iter_rows_reads_all_panel_rows():
    # Robust to a missing final newline: compare against non-blank physical lines.
    with open(SAMPLE) as f:
        expected = sum(1 for line in f if line.strip())
    assert sum(1 for _ in iter_rows(SAMPLE)) == expected == 757
