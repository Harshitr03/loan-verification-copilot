import asyncio
import os
from datetime import datetime, timezone
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


@requires_mongo
@pytest.mark.asyncio
async def test_concurrent_appends_do_not_fork_the_chain(real_db):
    # F1: overlapping appends must serialize; on real Mongo the awaits actually
    # yield, so without the lock the prev_hash linkage forks and verify false-breaks.
    ch = HashChain(AuditEntry, "audit")
    await asyncio.gather(*[
        ch.append(event_type=f"e{i}", entity_type="loan", entity_id="L", actor="op",
                  payload={"i": i})
        for i in range(25)
    ])
    seqs = sorted(e.seq for e in await AuditEntry.find().to_list())
    assert seqs == list(range(1, 26))
    assert (await ch.verify())["ok"] is True


@requires_mongo
@pytest.mark.asyncio
async def test_nested_decimal_and_datetime_in_payload_survive(real_db):
    # F2: a datetime/Decimal nested in a hashed field must not drift through BSON.
    ch = HashChain(AuditEntry, "audit")
    await ch.append(event_type="edit", entity_type="loan", entity_id="L", actor="op",
                    payload={"old": Decimal("5.25"), "at": datetime.now(timezone.utc)})
    assert (await ch.verify())["ok"] is True
