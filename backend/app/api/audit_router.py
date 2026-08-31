from fastapi import APIRouter, Depends
from backend.app.audit import verify_chain
from backend.app.auth import get_current_user

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/verify")
async def verify(_=Depends(get_current_user)):
    return await verify_chain()
