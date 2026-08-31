from backend.app.models import Dataset, RawRecord, Loan
from backend.app.ingestion.parse import read_upload
from backend.app.ingestion.normalize import to_canonical, to_storable
from backend.app import audit


async def _store_siblings(dataset_id, file, file_type):
    if file is None:
        return
    filename, content = file
    for i, raw in enumerate(read_upload(content, filename), start=1):
        await RawRecord(dataset_id=dataset_id, row_number=i, raw=raw,
                        source_file=filename, file_type=file_type).insert()


async def ingest_dataset(loan_tape, source_system, uploaded_by,
                         servicer_update=None, document_manifest=None) -> Dataset:
    tape_name, tape_bytes = loan_tape
    ds = await Dataset(filename=tape_name, file_type="loan_tape",
                       source_system=source_system, uploaded_by=uploaded_by,
                       status="imported").insert()
    dsid = str(ds.id)

    rows = read_upload(tape_bytes, tape_name)
    imported = 0
    failures = []
    for i, raw in enumerate(rows, start=1):
        rr = await RawRecord(dataset_id=dsid, row_number=i, raw=raw,
                             source_file=tape_name, file_type="loan_tape").insert()
        canon, reason = to_canonical(raw, source_system)
        if canon is None:
            failures.append({"row_number": i, "reason": reason})
            continue
        await Loan(dataset_id=dsid, normalized_from_raw_id=str(rr.id),
                   lifecycle_state="imported", validation_status="pending",
                   **to_storable(canon)).insert()
        imported += 1

    await _store_siblings(dsid, servicer_update, "servicer_update")
    await _store_siblings(dsid, document_manifest, "document_manifest")

    ds.row_count = len(rows)
    ds.imported_count = imported
    ds.failed_count = len(failures)
    ds.failures = failures
    await ds.save()

    await audit.append("file_uploaded", "dataset", dsid, uploaded_by,
                       {"filename": tape_name, "row_count": len(rows),
                        "imported": imported, "failed": len(failures),
                        "has_servicer_update": servicer_update is not None,
                        "has_document_manifest": document_manifest is not None})
    return ds
