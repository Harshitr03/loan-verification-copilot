from datetime import datetime, timezone
from backend.app.config import get_settings
from backend.app.ai.mock import MockProvider
from backend.app.models import Exception as Exc, AIRecommendation
from backend.app import audit


def get_provider():
    s = get_settings()
    if s.anthropic_api_key:
        from backend.app.ai.claude import ClaudeProvider
        return ClaudeProvider(s.anthropic_api_key)
    return MockProvider()


def _bundle(exc: Exc) -> dict:
    return {"rule_id": exc.rule_id, "field": exc.field, "observed_value": exc.observed_value,
            "expected": exc.expected, "sibling_value": exc.sibling_value, "message": exc.message}


async def run_ai(exception_id, kind, actor) -> AIRecommendation:
    exc = await Exc.get(exception_id)
    if exc is None:
        raise ValueError("exception not found")
    b = _bundle(exc)
    try:
        res = getattr(get_provider(), kind)(b)          # explain/suggest/compare/notes/classify
    except Exception:                                    # finding #8: Claude down -> Mock fallback
        res = getattr(MockProvider(), kind)(b)
        res.provider = "mock (claude-fallback)"
    rec = await AIRecommendation(
        exception_id=exception_id, loan_id=exc.loan_id, kind=kind, provider=res.provider,
        model=res.model, prompt=res.prompt or str(b), response=res.text,
        suggested_value=res.suggested_value, confidence=res.confidence, decision="pending").insert()
    exc.ai_recommendation_id = str(rec.id)
    await exc.save()
    await audit.append("ai_recommendation_generated", "exception", exception_id, actor,
                       {"kind": kind, "provider": res.provider})
    return rec


async def decide_ai(rec_id, decision, actor) -> AIRecommendation:
    rec = await AIRecommendation.get(rec_id)
    if rec is None:
        raise ValueError("recommendation not found")
    rec.decision = decision
    rec.decided_by = actor
    rec.decided_at = datetime.now(timezone.utc)
    await rec.save()
    await audit.append("ai_decision", "ai_recommendation", rec_id, actor, {"decision": decision})
    return rec
