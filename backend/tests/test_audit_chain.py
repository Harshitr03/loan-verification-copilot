import pytest
from backend.app import audit


@pytest.mark.asyncio
async def test_wrapper_appends_and_verifies(client, db, reviewer_headers):
    await audit.append("file_uploaded", "dataset", "D1", "op", {"filename": "x.csv"})
    r = await client.get("/audit/verify", headers=reviewer_headers)
    assert r.status_code == 200 and r.json()["ok"] is True


@pytest.mark.asyncio
async def test_verify_requires_auth(client, db):
    r = await client.get("/audit/verify")
    assert r.status_code == 401
