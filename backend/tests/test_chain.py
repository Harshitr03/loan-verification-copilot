import pytest
from backend.app.chain import HashChain
from backend.app.models import AuditEntry
# NOTE: the concurrency (F1) and nested-Decimal (F2) regressions live in the
# real-Mongo lane (test_integration_chain.py) — mongomock's ops don't yield to
# the event loop and keep full datetime/Decimal precision, so it hides both
# classes of bug (the same reason it hid the original 1a timestamp bug).


@pytest.mark.asyncio
async def test_append_links_and_seq_is_atomic(db):
    ch = HashChain(AuditEntry, "audit")
    a = await ch.append(event_type="e1", entity_type="loan", entity_id="LN1", actor="op", payload={"v": 1})
    b = await ch.append(event_type="e2", entity_type="loan", entity_id="LN1", actor="op", payload={"v": 2})
    assert (a.seq, b.seq) == (1, 2)
    assert a.prev_hash == "" and b.prev_hash == a.entry_hash and b.entry_hash != a.entry_hash


@pytest.mark.asyncio
async def test_verify_detects_tampering(db):
    ch = HashChain(AuditEntry, "audit")
    await ch.append(event_type="e1", entity_type="loan", entity_id="LN1", actor="op", payload={"v": 1})
    await ch.append(event_type="e2", entity_type="loan", entity_id="LN1", actor="op", payload={"v": 2})
    assert (await ch.verify())["ok"] is True
    tail = await AuditEntry.find_one(AuditEntry.seq == 2)
    tail.payload = {"v": 999}
    await tail.save()                                      # tamper
    res = await ch.verify()
    assert res["ok"] is False and res["broken_at"] == 2


@pytest.mark.asyncio
async def test_ts_iso_is_hashed_not_datetime(db):
    # regression for finding 1a: the hash must not depend on the ms-lossy datetime
    ch = HashChain(AuditEntry, "audit")
    e = await ch.append(event_type="e", entity_type="loan", entity_id="L", actor="op", payload={})
    e.timestamp = e.timestamp.replace(microsecond=0)       # simulate BSON ms truncation drift
    await e.save()
    assert (await ch.verify())["ok"] is True                # still valid: timestamp isn't hashed
