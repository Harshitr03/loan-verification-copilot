import csv
import io
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from backend.app.models import Loan, Exception as Exc, VerifiedRecord, AuditEntry
from backend.app.auth import get_current_user
from backend.app.audit import verify_chain
from data._serialize import CANONICAL_COLUMNS

router = APIRouter(tags=["public"])


@router.get("/loans")
async def list_loans(dataset_id: str | None = None, status: str | None = None,
                     skip: int = 0, limit: int = 50, _=Depends(get_current_user)):
    q = {}
    if dataset_id:
        q["dataset_id"] = dataset_id
    if status:
        q["lifecycle_state"] = status
    cur = Loan.find(q)
    total = await cur.count()
    items = await cur.skip(skip).limit(limit).to_list()
    return {"items": [l.model_dump(mode="json") for l in items], "total": total}


@router.get("/loans/{loan_id}")
async def get_loan(loan_id: str, _=Depends(get_current_user)):
    loan = await Loan.find_one(Loan.loan_id == loan_id)
    if loan is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "loan not found")
    exceptions = await Exc.find(Exc.loan_id == loan_id).to_list()
    return {"loan": loan.model_dump(mode="json"), "exceptions": [e.model_dump(mode="json") for e in exceptions]}


@router.get("/exceptions")
async def list_exceptions(status: str | None = None, severity: str | None = None,
                          type: str | None = None, loan_id: str | None = None,
                          q: str | None = None, skip: int = 0, limit: int = 50,
                          _=Depends(get_current_user)):
    query = {}
    if status:
        query["status"] = status
    if severity:
        query["severity"] = severity
    if type:
        query["type"] = type
    if loan_id:
        query["loan_id"] = loan_id
    cur = Exc.find(query)
    total = await cur.count()
    rows = await cur.to_list()
    if q:                                       # search by loan/borrower id substring
        rows = [e for e in rows if q in (e.loan_id or "")]
    items = rows[skip:skip + limit]
    return {"items": [e.model_dump(mode="json") for e in items], "total": len(rows) if q else total}


@router.get("/verified-loans")
async def list_verified(skip: int = 0, limit: int = 50, _=Depends(get_current_user)):
    cur = VerifiedRecord.find()
    total = await cur.count()
    items = await cur.sort(+VerifiedRecord.seq).skip(skip).limit(limit).to_list()
    return {"items": [v.model_dump(mode="json") for v in items], "total": total}


@router.get("/verified-loans/export")
async def export_verified(format: str = "csv", _=Depends(get_current_user)):
    vrs = await VerifiedRecord.find().sort(+VerifiedRecord.seq).to_list()
    if format == "json":
        return {"items": [v.canonical_data for v in vrs]}
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(CANONICAL_COLUMNS)
    for v in vrs:
        w.writerow([v.canonical_data.get(c, "") for c in CANONICAL_COLUMNS])
    return Response(content=buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=verified-loans.csv"})


@router.get("/verified-loans/{loan_id}")
async def get_verified(loan_id: str, _=Depends(get_current_user)):
    v = await VerifiedRecord.find_one(VerifiedRecord.loan_id == loan_id)
    if v is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "verified record not found")
    return v.model_dump(mode="json")


@router.get("/audit/export")
async def export_audit(_=Depends(get_current_user)):
    entries = await AuditEntry.find().sort(+AuditEntry.seq).to_list()
    return {"items": [e.model_dump(mode="json") for e in entries], "chain": await verify_chain()}


@router.get("/audit/{loan_id}")
async def audit_for_loan(loan_id: str, _=Depends(get_current_user)):
    entries = await AuditEntry.find(AuditEntry.entity_type == "loan",
                                    AuditEntry.entity_id == loan_id).sort(+AuditEntry.seq).to_list()
    return {"items": [e.model_dump(mode="json") for e in entries], "chain": await verify_chain()}


@router.get("/summary")
async def summary(_=Depends(get_current_user)):
    from backend.app.models import Dataset

    async def _c(model, q=None):
        return await model.find(q or {}).count()

    by_status, by_sev = {}, {}
    for s in ("open", "resolved", "accepted", "rejected"):
        by_status[s] = await _c(Exc, {"status": s})
    for sv in ("low", "medium", "high", "critical"):
        by_sev[sv] = await _c(Exc, {"severity": sv})
    datasets = await Dataset.find().to_list()
    scores = [d.quality_score for d in datasets if d.quality_score is not None]
    return {"datasets": len(datasets), "loans_total": await _c(Loan),
            "verified_total": await _c(VerifiedRecord),
            "exceptions_by_status": by_status, "exceptions_by_severity": by_sev,
            "avg_quality_score": round(sum(scores) / len(scores), 4) if scores else None}
