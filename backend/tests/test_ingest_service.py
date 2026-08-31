import pytest
from backend.app.ingestion.service import ingest_dataset
from backend.app.models import Loan, RawRecord, AuditEntry


@pytest.mark.asyncio
async def test_ingest_stores_raw_loans_counts_and_siblings(db):
    tape = b"loan_id,original_principal,origination_date\nLN1,100.00,2020-01-15\n,50,2020-01-15\n"
    srv = b"loan_id,current_balance\nLN1,90.00\n"
    man = b"loan_id,document_status\nLN1,COMPLETE\n"
    ds = await ingest_dataset(("tape.csv", tape), "ORIG_SYS", "op",
                              servicer_update=("srv.csv", srv), document_manifest=("man.csv", man))
    assert ds.row_count == 2 and ds.imported_count == 1 and ds.failed_count == 1
    loans = await Loan.find(Loan.dataset_id == str(ds.id)).to_list()
    assert len(loans) == 1 and loans[0].loan_id == "LN1" and loans[0].normalized_from_raw_id
    assert await RawRecord.find(RawRecord.dataset_id == str(ds.id),
                                RawRecord.file_type == "servicer_update").count() == 1
    assert ds.failures[0]["reason"]      # the empty-loan_id row
    # one summary event, not per-record:
    assert await AuditEntry.find(AuditEntry.event_type == "file_uploaded").count() == 1
