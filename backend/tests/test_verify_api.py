import pytest
from backend.app.models import Loan, VerifiedRecord, AuditEntry, Exception as Exc


@pytest.mark.asyncio
async def test_reviewer_verifies_loan(client, db, reviewer_headers):
    await Loan(loan_id="LN1", dataset_id="D1", validation_status="validated",
               lifecycle_state="validated").insert()
    r = await client.post("/loans/LN1/verify", headers=reviewer_headers)
    assert r.status_code == 200 and r.json()["record_hash"]
    loan = await Loan.find_one(Loan.loan_id == "LN1")
    assert loan.lifecycle_state == "verified"
    assert await VerifiedRecord.find(VerifiedRecord.loan_id == "LN1").count() == 1
    assert await AuditEntry.find(AuditEntry.event_type == "verified_record_created").count() == 1
    # second verify -> 409
    r2 = await client.post("/loans/LN1/verify", headers=reviewer_headers)
    assert r2.status_code == 409


@pytest.mark.asyncio
async def test_verify_blocked_by_open_exception(client, db, reviewer_headers):
    await Loan(loan_id="LN2", dataset_id="D1", validation_status="validated",
               lifecycle_state="validated").insert()
    await Exc(loan_id="LN2", dataset_id="D1", rule_id="non_negative_amounts", type="ROW",
              severity="high", source="rule", field="current_balance",
              observed_value="-5", expected=">= 0", message="negative", status="open").insert()
    # open exception -> verify is refused
    r = await client.post("/loans/LN2/verify", headers=reviewer_headers)
    assert r.status_code == 409
    assert "open exception" in r.json()["detail"]
    assert await VerifiedRecord.find(VerifiedRecord.loan_id == "LN2").count() == 0
    # resolve it, then verify succeeds
    await client.post("/exceptions/{}/resolve".format(
        (await Exc.find_one(Exc.loan_id == "LN2")).id),
        json={"action": "approve"}, headers=reviewer_headers)
    r2 = await client.post("/loans/LN2/verify", headers=reviewer_headers)
    assert r2.status_code == 200 and r2.json()["record_hash"]


@pytest.mark.asyncio
async def test_consumer_cannot_verify(client, db, consumer_headers):
    await Loan(loan_id="LN1", dataset_id="D1", validation_status="validated").insert()
    r = await client.post("/loans/LN1/verify", headers=consumer_headers)
    assert r.status_code == 403
