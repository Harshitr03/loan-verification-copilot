from fastapi import APIRouter, Depends
from pydantic import BaseModel
from backend.app.auth import require_role
from backend.app.ai.service import run_ai, decide_ai, get_provider
from backend.app.models import Exception as Exc

router = APIRouter(tags=["ai"])


class AIIn(BaseModel):
    kind: str


class DecisionIn(BaseModel):
    decision: str


class SummarizeIn(BaseModel):
    dataset_id: str


class GenRuleIn(BaseModel):
    text: str


@router.post("/exceptions/{exc_id}/ai")
async def exception_ai(exc_id: str, body: AIIn, user=Depends(require_role("reviewer"))):
    rec = await run_ai(exc_id, body.kind, user.username)
    return rec.model_dump(mode="json")


@router.post("/ai/{rec_id}/decision")
async def ai_decision(rec_id: str, body: DecisionIn, user=Depends(require_role("reviewer"))):
    rec = await decide_ai(rec_id, body.decision, user.username)
    return rec.model_dump(mode="json")


@router.post("/ai/summarize")
async def ai_summarize(body: SummarizeIn, user=Depends(require_role("reviewer"))):
    excs = await Exc.find(Exc.dataset_id == body.dataset_id).to_list()
    res = get_provider().summarize([{"rule_id": e.rule_id} for e in excs])
    return {"text": res.text}


@router.post("/ai/generate-rule")
async def ai_generate_rule(body: GenRuleIn, user=Depends(require_role("reviewer"))):
    res = get_provider().generate_rule(body.text)
    return {"candidate": res.text}      # candidate-only; reviewer-gated before activation
