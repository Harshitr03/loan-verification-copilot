from beanie import PydanticObjectId
from backend.app.models import Dataset, RawRecord, Loan
from backend.app.ingestion.parse import read_upload
from backend.app.ingestion.normalize import to_canonical, to_storable
from backend.app import audit


async def _insert_chunked(model, docs, size=1000):
    """Batch insert to keep round-trips low (fast against remote Mongo/Atlas)."""
    for i in range(0, len(docs), size):
        await model.insert_many(docs[i:i + size])


async def _store_siblings(dataset_id, file, file_type):
    if file is None:
        return
    filename, content = file
    docs = [RawRecord(dataset_id=dataset_id, row_number=i, raw=raw,
                      source_file=filename, file_type=file_type)
            for i, raw in enumerate(read_upload(content, filename), start=1)]
    await _insert_chunked(RawRecord, docs)


async def ingest_dataset(loan_tape, source_system, uploaded_by,
                         servicer_update=None, document_manifest=None) -> Dataset:
    tape_name, tape_bytes = loan_tape
    ds = await Dataset(filename=tape_name, file_type="loan_tape",
                       source_system=source_system, uploaded_by=uploaded_by,
                       status="imported").insert()
    dsid = str(ds.id)

    rows = read_upload(tape_bytes, tape_name)
    raws, loans, failures = [], [], []
    for i, raw in enumerate(rows, start=1):
        # pre-assign the raw record's _id so the loan can reference it without a
        # separate insert round-trip per row (that was the slow path).
        rid = PydanticObjectId()
        raws.append(RawRecord(id=rid, dataset_id=dsid, row_number=i, raw=raw,
                              source_file=tape_name, file_type="loan_tape"))
        canon, reason = to_canonical(raw, source_system)
        if canon is None:
            failures.append({"row_number": i, "reason": reason})       # un-normalizable row
            continue
        loans.append(Loan(dataset_id=dsid, normalized_from_raw_id=str(rid),
                          lifecycle_state="imported", validation_status="pending",
                          **to_storable(canon)))

    await _insert_chunked(RawRecord, raws)
    await _insert_chunked(Loan, loans)
    await _store_siblings(dsid, servicer_update, "servicer_update")
    await _store_siblings(dsid, document_manifest, "document_manifest")

    ds.row_count = len(rows)
    ds.imported_count = len(loans)
    ds.failed_count = len(failures)
    ds.failures = failures
    await ds.save()

    await audit.append("file_uploaded", "dataset", dsid, uploaded_by,
                       {"filename": tape_name, "row_count": len(rows),
                        "imported": len(loans), "failed": len(failures),
                        "has_servicer_update": servicer_update is not None,
                        "has_document_manifest": document_manifest is not None})
    return ds
