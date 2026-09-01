"""Repeatable demo-state seed.

Yields a good `docker compose up` demo without any manual clicking: ensures the
deterministic loan package is ingested + validated, then walks a fixed set of loans
through the real reviewer flow (resolve every open exception -> verify) so the
Consumer dashboard and audit chain look alive.

Idempotent: skips once enough verified records exist, and never re-ingests when a
dataset is already present. Uses the domain services directly (same code paths the
HTTP routers use), so the audit trail it produces is indistinguishable from a human's.
"""
import os
from datetime import datetime, timezone

from backend.app.models import Loan, Exception as Exc, Dataset, VerifiedRecord
from backend.app.ingestion.service import ingest_dataset
from backend.app.validation.runner import run_validation
from backend.app.verification.builder import build_verified_record
from backend.app import audit

REVIEWER = "reviewer"                       # actor stamped on seeded decisions
_DATA_DIR = "data"                          # generated package baked into the image


def _pair(name: str):
    path = os.path.join(_DATA_DIR, name)
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        return (name, f.read())


async def _ensure_data() -> None:
    """Ingest + validate the deterministic package, but only on a truly empty DB."""
    if await Dataset.find_one():
        return
    tape = _pair("loan_tape.csv")
    if tape is None:
        return                              # nothing to seed from; leave DB empty
    ds = await ingest_dataset(tape, source_system="ORIG_SYS", uploaded_by="operator",
                              servicer_update=_pair("servicer_update.csv"),
                              document_manifest=_pair("document_manifest.csv"))
    await run_validation(str(ds.id))


async def _approve(exc: Exc, now: str) -> None:
    exc.status = "resolved"
    exc.resolution = {"action": "approve", "by": REVIEWER, "at": now}
    await exc.save()
    await audit.append("loan_approved", "loan", exc.loan_id, REVIEWER, {"exception": str(exc.id)})


async def _edit(loan: Loan, exc: Exc, now: str) -> bool:
    """Correct one field so the trail shows a real 'field_edited' event. Restricted to
    document_status: it's a free-form string, so the corrected value is always type-valid
    (unlike numeric/date fields, whose `expected` is a constraint string, not a value)."""
    if exc.field != "document_status":
        return False
    old = getattr(loan, exc.field, None)
    newv = "COMPLETE"
    setattr(loan, exc.field, newv)
    await loan.save()
    exc.status = "accepted"
    exc.resolution = {"action": "edit", "field": exc.field, "old_value": str(old),
                      "new_value": str(newv), "by": REVIEWER, "at": now}
    await exc.save()
    await audit.append("field_edited", "loan", loan.loan_id, REVIEWER,
                       {"field": exc.field, "old": str(old), "new": str(newv)})
    return True


async def seed_demo(target: int = 10) -> int:
    """Verify up to `target` loans through the real flow. Returns how many it added."""
    already = await VerifiedRecord.count()
    if already >= target:
        return 0
    await _ensure_data()

    loans = await Loan.find(Loan.lifecycle_state == "validated").sort(+Loan.loan_id).to_list()
    added = 0
    for i, loan in enumerate(loans):
        if already + added >= target:
            break
        try:
            now = datetime.now(timezone.utc).isoformat()
            open_excs = await Exc.find(Exc.loan_id == loan.loan_id,
                                       Exc.dataset_id == loan.dataset_id,
                                       Exc.status == "open").to_list()
            if open_excs and loan.lifecycle_state == "validated":
                loan.lifecycle_state = "in_review"
                await loan.save()
            # variety: on every 3rd loan, correct a document_status exception (field_edited
            # event); approve the rest. Every open exception must clear before verify.
            edited = False
            for exc in open_excs:
                if not edited and i % 3 == 0 and await _edit(loan, exc, now):
                    edited = True
                else:
                    await _approve(exc, now)
            vr = await build_verified_record(loan, REVIEWER)
            loan.lifecycle_state = "verified"
            await loan.save()
            await audit.append("verified_record_created", "loan", loan.loan_id, REVIEWER,
                               {"record_hash": vr.record_hash, "seq": vr.seq})
            added += 1
        except Exception as e:              # noqa: BLE001 — one bad row must not abort the batch
            print(f"[demo_seed] skipped {loan.loan_id}: {e}")
    return added
