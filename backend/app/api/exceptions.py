from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from backend.app.models import Exception as Exc, Loan, AuditEntry
from backend.app.auth import require_role, get_current_user
from backend.app import audit
from backend.app.ingestion.normalize import _money, _date

router = APIRouter(tags=["exceptions"])

ALLOWED_EDIT_FIELDS = {"interest_rate", "current_balance", "payment_status", "days_past_due",
                       "borrower_state", "loan_purpose", "maturity_date", "document_status"}


class ResolveIn(BaseModel):
    action: str                      # edit | approve | reject | request_correction
    field: str | None = None
    new_value: str | None = None
    note: str | None = None


def _coerce(field, value):
    if field in ("interest_rate", "current_balance"):
        return _money(value)
    if field == "days_past_due":
        return int(value) if value not in (None, "") else None
    if field == "maturity_date":
        return _date(value)
    return value


@router.post("/exceptions/{exc_id}/resolve")
async def resolve(exc_id: str, body: ResolveIn, user=Depends(require_role("reviewer"))):
    exc = await Exc.get(exc_id)
    if exc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "exception not found")
    loan = await Loan.find_one(Loan.loan_id == exc.loan_id, Loan.dataset_id == exc.dataset_id)
    if loan and loan.lifecycle_state == "validated":
        loan.lifecycle_state = "in_review"
        await loan.save()
    now = datetime.now(timezone.utc).isoformat()

    if body.action == "edit":
        if body.field not in ALLOWED_EDIT_FIELDS:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"field {body.field} not editable")
        old = getattr(loan, body.field, None) if loan else None
        newv = _coerce(body.field, body.new_value)
        if loan:
            setattr(loan, body.field, newv)
            await loan.save()
        exc.status = "accepted"
        exc.resolution = {"action": "edit", "field": body.field, "old_value": str(old),
                          "new_value": str(newv), "by": user.username, "at": now}
        await audit.append("field_edited", "loan", exc.loan_id, user.username,
                           {"field": body.field, "old": str(old), "new": str(newv)})
    elif body.action == "approve":
        exc.status = "resolved"
        exc.resolution = {"action": "approve", "by": user.username, "at": now}
        await audit.append("loan_approved", "loan", exc.loan_id, user.username, {"exception": exc_id})
    elif body.action == "reject":
        exc.status = "rejected"
        exc.resolution = {"action": "reject", "by": user.username, "at": now}
        await audit.append("loan_rejected", "loan", exc.loan_id, user.username, {"exception": exc_id})
    elif body.action == "request_correction":
        exc.status = "open"
        exc.resolution = {"action": "request_correction", "note": body.note, "by": user.username, "at": now}
        await audit.append("comment_added", "loan", exc.loan_id, user.username, {"note": body.note or ""})
    else:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"unknown action {body.action}")

    await exc.save()
    return exc.model_dump(mode="json")


@router.get("/loans/{loan_id}/history")
async def loan_history(loan_id: str, _=Depends(get_current_user)):
    entries = await AuditEntry.find(AuditEntry.entity_type == "loan",
                                    AuditEntry.entity_id == loan_id).sort(+AuditEntry.seq).to_list()
    return {"items": [e.model_dump(mode="json") for e in entries]}
