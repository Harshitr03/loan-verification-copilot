import pytest
from backend.app.models import Loan, VerifiedRecord, AuditEntry


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
async def test_consumer_cannot_verify(client, db, consumer_headers):
    await Loan(loan_id="LN1", dataset_id="D1", validation_status="validated").insert()
    r = await client.post("/loans/LN1/verify", headers=consumer_headers)
    assert r.status_code == 403
