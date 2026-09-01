import csv
import pytest
from data.generate import generate
from backend.app.ingestion.service import ingest_dataset
from backend.app.validation.runner import run_validation
from backend.app.models import Exception as Exc, AuditEntry, Loan


@pytest.mark.asyncio
async def test_runner_reproduces_full_ground_truth_superset(tmp_path, db):
    generate(str(tmp_path), rows=400, seed=7)     # tape + servicer + manifest + rules + ground truth
    read = lambda n: (n, (tmp_path / n).read_bytes())
    ds = await ingest_dataset(read("loan_tape.csv"), "ORIG_SYS", "op",
                              servicer_update=read("servicer_update.csv"),
                              document_manifest=read("document_manifest.csv"))
    await run_validation(str(ds.id), rules_path=str(tmp_path / "validation_rules.json"))

    found = {(e.loan_id, e.rule_id) async for e in Exc.find(Exc.dataset_id == str(ds.id))}
    gt = set()
    with open(tmp_path / "ground_truth_exceptions.csv") as f:
        for r in csv.DictReader(f):
            gt.add((r["loan_id"], r["rule_id"]))
    # Oracle: for every loan we actually imported, all its ground-truth findings are
    # detected. The only rows out of scope are *failed imports* — rows whose final
    # loan_id is blank (required_fields blanked the primary key); their findings live
    # in dataset.failures, not exceptions (Module A, spec §6). No per-rule carve-out:
    # all 15 rule types are exercised on the ingested loans.
    ingested = {l.loan_id async for l in Loan.find(Loan.dataset_id == str(ds.id))}
    gt_checkable = {(lid, rid) for (lid, rid) in gt if lid in ingested}
    assert gt_checkable <= found, f"missed: {sorted(gt_checkable - found)[:10]}"
    # sanity: the full rule vocabulary actually fired (not a trivially-empty check)
    assert len({rid for _, rid in gt_checkable}) >= 13
    # one summary validation event, none per-exception:
    assert await AuditEntry.find(AuditEntry.event_type == "validation_executed").count() == 1
    assert await AuditEntry.find(AuditEntry.event_type == "exception_created").count() == 0


@pytest.mark.asyncio
async def test_field_availability_gating_no_borrower_no_manifest(db):
    # FNMA-shaped upload: has loan_id/principal/dates but NO borrower_id and NO manifest.
    # required_fields must not flood on borrower_id, and document_status_present must be gated.
    from backend.app.ingestion.service import ingest_dataset
    tape = (b"loan_id,original_principal,origination_date,maturity_date,interest_rate,current_balance,payment_status,days_past_due,borrower_state\n"
            + b"".join(
                f"LN{i:03d},250000.00,2020-01-15,2050-01-15,5.25,200000.00,CURRENT,0,CA\n".encode()
                for i in range(20)))
    ds = await ingest_dataset(("t.csv", tape), "FNMA_SF_LPD", "op")   # no siblings
    res = await run_validation(str(ds.id))
    flagged = {(e.loan_id, e.rule_id) async for e in Exc.find(Exc.dataset_id == str(ds.id))}
    assert not any(rid == "document_status_present" for _, rid in flagged)   # gated
    assert not any(rid == "required_fields" for _, rid in flagged)           # borrower_id not required
    assert "required_fields:borrower_id" in res["gated_rules"]
    assert res["quality_score"] == 1.0     # clean FNMA-shaped rows now score 100%, not 0%
