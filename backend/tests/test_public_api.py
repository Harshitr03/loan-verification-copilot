import csv
import io
import pytest
from decimal import Decimal
from data._serialize import CANONICAL_COLUMNS
from backend.app.models import Loan, Exception as Exc


async def _seed():
    await Loan(loan_id="LN1", dataset_id="D1", original_principal=Decimal("100.00"),
               lifecycle_state="validated", validation_status="validated").insert()
    await Loan(loan_id="LN2", dataset_id="D1", lifecycle_state="validated").insert()
    await Exc(loan_id="LN1", dataset_id="D1", rule_id="r1", type="ROW", severity="high",
              source="rule", field="f", observed_value="x", expected="y", message="m",
              status="open").insert()
    await Exc(loan_id="LN2", dataset_id="D1", rule_id="r2", type="ROW", severity="low",
              source="rule", field="f", observed_value="x", expected="y", message="m",
              status="resolved").insert()


@pytest.mark.asyncio
async def test_loans_and_exceptions_reads(client, db, reviewer_headers):
    await _seed()
    assert (await client.get("/loans", headers=reviewer_headers)).json()["total"] == 2
    d = await client.get("/loans/LN1", headers=reviewer_headers)
    assert d.status_code == 200 and len(d.json()["exceptions"]) == 1
    assert (await client.get("/loans/NOPE", headers=reviewer_headers)).status_code == 404
    assert (await client.get("/exceptions?severity=high", headers=reviewer_headers)).json()["total"] == 1
    assert (await client.get("/exceptions?status=resolved", headers=reviewer_headers)).json()["total"] == 1
    assert (await client.get("/loans")).status_code == 401


@pytest.mark.asyncio
async def test_summary(client, db, reviewer_headers):
    await _seed()
    s = (await client.get("/summary", headers=reviewer_headers)).json()
    assert s["loans_total"] == 2 and s["exceptions_by_severity"]["high"] == 1


@pytest.mark.asyncio
async def test_verify_export_and_audit(client, db, reviewer_headers):
    await Loan(loan_id="LN1", dataset_id="D1", original_principal=Decimal("100.00"),
               lifecycle_state="validated", validation_status="validated").insert()
    await client.post("/loans/LN1/verify", headers=reviewer_headers)
    assert (await client.get("/verified-loans", headers=reviewer_headers)).json()["total"] == 1
    assert (await client.get("/verified-loans/LN1", headers=reviewer_headers)).status_code == 200
    exp = await client.get("/verified-loans/export?format=csv", headers=reviewer_headers)
    assert "text/csv" in exp.headers["content-type"]
    rows = list(csv.reader(io.StringIO(exp.text)))
    assert rows[0] == CANONICAL_COLUMNS and len(rows) - 1 == 1
    aud = await client.get("/audit/LN1", headers=reviewer_headers)
    assert aud.status_code == 200 and aud.json()["chain"]["ok"] is True


@pytest.mark.asyncio
async def test_ids_serialize_as_strings(client, db, reviewer_headers):
    # regression: model_dump(mode="json") must render ObjectId `id` as a usable string
    # (python-mode model_dump serializes it to {} through FastAPI, breaking every id-keyed call)
    await _seed()
    body = (await client.get("/exceptions", headers=reviewer_headers)).json()
    assert isinstance(body["items"][0]["id"], str) and len(body["items"][0]["id"]) >= 12
