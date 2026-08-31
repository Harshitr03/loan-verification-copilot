from backend.app.ingestion.parse import read_upload


def test_read_upload_preserves_columns_and_values():
    csv = b"loan_id,current_balance\nLN1,100.00\nLN2,\n"
    rows = read_upload(csv, "loan_tape.csv")
    assert rows == [{"loan_id": "LN1", "current_balance": "100.00"},
                    {"loan_id": "LN2", "current_balance": ""}]     # blanks kept, not NaN
