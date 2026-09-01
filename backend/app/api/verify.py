from fastapi import APIRouter, Depends, HTTPException, status
from backend.app.models import Loan, Exception as Exc
from backend.app.auth import require_role
from backend.app.verification.builder import build_verified_record
from backend.app import audit

router = APIRouter(tags=["verify"])


@router.post("/loans/{loan_id}/verify")
async def verify_loan(loan_id: str, user=Depends(require_role("reviewer"))):
    loan = await Loan.find_one(Loan.loan_id == loan_id)
    if loan is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "loan not found")
    if loan.lifecycle_state == "verified":
        raise HTTPException(status.HTTP_409_CONFLICT, "loan already verified")
    # A record can only be "verified/trusted" once every open exception on it has been
    # adjudicated (accepted/resolved/rejected). Verifying over open defects would make the
    # trust claim meaningless — so gate on it and tell the reviewer what's left.
    open_exc = await Exc.find(Exc.loan_id == loan_id, Exc.dataset_id == loan.dataset_id,
                              Exc.status == "open").count()
    if open_exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"cannot verify: {open_exc} open exception(s) must be resolved first")
    vr = await build_verified_record(loan, user.username)
    loan.lifecycle_state = "verified"
    await loan.save()
    await audit.append("verified_record_created", "loan", loan_id, user.username,
                       {"record_hash": vr.record_hash, "seq": vr.seq})
    return {"loan_id": loan_id, "record_hash": vr.record_hash, "seq": vr.seq}
