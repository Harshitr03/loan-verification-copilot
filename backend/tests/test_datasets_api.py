import pytest


@pytest.mark.asyncio
async def test_operator_uploads_3_files_and_lists(client, db, operator_headers, consumer_headers):
    tape = b"loan_id,original_principal,origination_date\nLN1,100.00,2020-01-15\n"
    srv = b"loan_id,current_balance\nLN1,90.00\n"
    man = b"loan_id,document_status\nLN1,COMPLETE\n"
    r = await client.post(
        "/datasets",
        data={"source_system": "ORIG_SYS"},
        files={"loan_tape": ("tape.csv", tape, "text/csv"),
               "servicer_update": ("srv.csv", srv, "text/csv"),
               "document_manifest": ("man.csv", man, "text/csv")},
        headers=operator_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["row_count"] == 1 and body["imported_count"] == 1

    lst = await client.get("/datasets", headers=operator_headers)
    assert lst.status_code == 200 and len(lst.json()["items"]) == 1

    detail = await client.get(f"/datasets/{body['dataset_id']}", headers=operator_headers)
    assert detail.status_code == 200 and detail.json()["source_system"] == "ORIG_SYS"


@pytest.mark.asyncio
async def test_consumer_cannot_upload(client, db, consumer_headers):
    r = await client.post("/datasets", data={"source_system": "S"},
                          files={"loan_tape": ("t.csv", b"loan_id\nLN1\n", "text/csv")},
                          headers=consumer_headers)
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_validate_endpoint_produces_exceptions(client, db, operator_headers):
    tape = (b"loan_id,interest_rate,original_principal,current_balance,payment_status,days_past_due\n"
            b"LN1,99.0,100000.00,50000.00,CURRENT,0\n")   # 99% rate -> interest_rate_range
    up = await client.post("/datasets", data={"source_system": "S"},
                           files={"loan_tape": ("t.csv", tape, "text/csv")}, headers=operator_headers)
    dsid = up.json()["dataset_id"]
    r = await client.post(f"/datasets/{dsid}/validate", headers=operator_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["exceptions"] >= 1 and 0 <= body["quality_score"] <= 1
