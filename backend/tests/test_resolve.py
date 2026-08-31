import pytest
from decimal import Decimal
from backend.app.models import Loan, Exception as Exc, AuditEntry


async def _seed(field="interest_rate", val=Decimal("99.0")):
    await Loan(loan_id="LN1", dataset_id="D1", interest_rate=val,
               validation_status="validated", lifecycle_state="validated").insert()
    return await Exc(loan_id="LN1", loan_ref="x", dataset_id="D1", rule_id="interest_rate_range",
                     type="ROW", severity="medium", source="rule", field=field,
                     observed_value="99.0", expected="2-36", message="x", status="open").insert()


@pytest.mark.asyncio
async def test_edit_applies_allowed_field_and_audits(client, db, reviewer_headers):
    e = await _seed()
    r = await client.post(f"/exceptions/{e.id}/resolve",
                          json={"action": "edit", "field": "interest_rate", "new_value": "5.25"},
                          headers=reviewer_headers)
    assert r.status_code == 200
    loan = await Loan.find_one(Loan.loan_id == "LN1")
    assert loan.interest_rate == Decimal("5.25")
    assert (await Exc.get(e.id)).status == "accepted"
    assert await AuditEntry.find(AuditEntry.event_type == "field_edited").count() == 1


@pytest.mark.asyncio
async def test_edit_rejects_disallowed_field(client, db, reviewer_headers):
    e = await _seed(field="loan_id")
    r = await client.post(f"/exceptions/{e.id}/resolve",
                          json={"action": "edit", "field": "loan_id", "new_value": "Z"},
                          headers=reviewer_headers)
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_approve_and_history(client, db, reviewer_headers):
    e = await _seed()
    await client.post(f"/exceptions/{e.id}/resolve",
                      json={"action": "edit", "field": "interest_rate", "new_value": "5.25"},
                      headers=reviewer_headers)
    await client.post(f"/exceptions/{e.id}/resolve", json={"action": "approve"},
                      headers=reviewer_headers)
    h = await client.get("/loans/LN1/history", headers=reviewer_headers)
    assert h.status_code == 200 and len(h.json()["items"]) >= 2
