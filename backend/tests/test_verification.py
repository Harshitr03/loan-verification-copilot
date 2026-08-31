import pytest
from backend.app.models import Loan, VerifiedRecord
from backend.app.verification.builder import build_verified_record
from backend.app.chain import HashChain


@pytest.mark.asyncio
async def test_verified_records_chain_orders_by_seq(db):
    l1 = await Loan(loan_id="LN1", dataset_id="D1", validation_status="validated").insert()
    l2 = await Loan(loan_id="LN2", dataset_id="D1", validation_status="validated").insert()
    v1 = await build_verified_record(l1, "rev")
    v2 = await build_verified_record(l2, "rev")
    assert (v1.seq, v2.seq) == (1, 2)
    assert v1.prev_record_hash == "" and v2.prev_record_hash == v1.record_hash
    chain = HashChain(VerifiedRecord, "verified", prev_field="prev_record_hash",
                      hash_field="record_hash", ts_field="verified_at")
    assert (await chain.verify())["ok"] is True
