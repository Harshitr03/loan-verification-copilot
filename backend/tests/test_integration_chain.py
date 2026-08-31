import os
from decimal import Decimal
import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from backend.app.db import init_db
from backend.app.chain import HashChain
from backend.app.models import AuditEntry, Loan

pytestmark = pytest.mark.integration

_URI = os.getenv("LVC_TEST_MONGODB_URI")
requires_mongo = pytest.mark.skipif(_URI is None, reason="set LVC_TEST_MONGODB_URI to run")


@pytest_asyncio.fixture
async def real_db():
    client = AsyncIOMotorClient(_URI)
    dbname = "lvc_itest"
    await client.drop_database(dbname)
    await init_db(client, dbname)
    yield client
    await client.drop_database(dbname)


@requires_mongo
@pytest.mark.asyncio
async def test_chain_survives_real_bson_roundtrip(real_db):
    ch = HashChain(AuditEntry, "audit")
    for i in range(3):
        await ch.append(event_type=f"e{i}", entity_type="loan", entity_id="LN1",
                        actor="op", payload={"i": i})
    # the case mongomock can't catch: ms-truncated datetime on reload
    assert (await ch.verify())["ok"] is True


@requires_mongo
@pytest.mark.asyncio
async def test_decimal128_roundtrips_intact(real_db):
    await Loan(loan_id="LN1", dataset_id="D1", original_principal=Decimal("123.45")).insert()
    got = await Loan.find_one(Loan.loan_id == "LN1")
    assert got.original_principal == Decimal("123.45")
