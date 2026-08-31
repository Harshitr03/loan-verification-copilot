"""Run the full pipeline against a real Mongo and export the §13 deliverables:
a verified-loans CSV and an audit-trail JSON. Doubles as an end-to-end smoke.

Usage: LVC_TEST_MONGODB_URI=mongodb://localhost:27017 python scripts/make_samples.py
"""
import asyncio
import csv
import json
import os
import tempfile
from motor.motor_asyncio import AsyncIOMotorClient
from backend.app.db import init_db
from backend.app.ingestion.service import ingest_dataset
from backend.app.validation.runner import run_validation
from backend.app.verification.builder import build_verified_record
from backend.app.models import Loan, Exception as Exc, VerifiedRecord, AuditEntry
from backend.app.audit import verify_chain
from backend.app import audit
from data._serialize import CANONICAL_COLUMNS
from data.generate import generate


async def main():
    d = tempfile.mkdtemp()
    generate(d, rows=5000, seed=1234)
    uri = os.environ.get("LVC_TEST_MONGODB_URI", "mongodb://localhost:27017")
    client = AsyncIOMotorClient(uri)
    await client.drop_database("lvc_samples")
    await init_db(client, "lvc_samples")

    read = lambda n: (n, open(os.path.join(d, n), "rb").read())
    ds = await ingest_dataset(read("loan_tape.csv"), "ORIG_SYS", "operator",
                              servicer_update=read("servicer_update.csv"),
                              document_manifest=read("document_manifest.csv"))
    res = await run_validation(str(ds.id), rules_path=os.path.join(d, "validation_rules.json"))

    flagged = {e.loan_id async for e in Exc.find(Exc.dataset_id == str(ds.id))}
    verified = 0
    async for l in Loan.find(Loan.dataset_id == str(ds.id)):
        if l.loan_id not in flagged and verified < 10:
            vr = await build_verified_record(l, "reviewer")
            l.lifecycle_state = "verified"
            await l.save()
            await audit.append("verified_record_created", "loan", l.loan_id, "reviewer",
                               {"record_hash": vr.record_hash, "seq": vr.seq})
            verified += 1

    os.makedirs("docs/samples", exist_ok=True)
    vrs = await VerifiedRecord.find().sort(+VerifiedRecord.seq).to_list()
    with open("docs/samples/verified-loans.sample.csv", "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(CANONICAL_COLUMNS)
        for v in vrs:
            w.writerow([v.canonical_data.get(c, "") for c in CANONICAL_COLUMNS])

    entries = await AuditEntry.find().sort(+AuditEntry.seq).to_list()
    chain = await verify_chain()
    with open("docs/samples/audit-trail.sample.json", "w") as f:
        json.dump({"chain_verified": chain, "entry_count": len(entries),
                   "entries": [{"seq": e.seq, "event_type": e.event_type,
                                "entity_type": e.entity_type, "entity_id": e.entity_id,
                                "actor": e.actor, "ts_iso": e.ts_iso,
                                "entry_hash": e.entry_hash} for e in entries[:40]]},
                  f, indent=2)

    print(f"validation={res} verified={verified} audit_entries={len(entries)} chain_ok={chain['ok']}")
    await client.drop_database("lvc_samples")


if __name__ == "__main__":
    asyncio.run(main())
