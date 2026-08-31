import pytest
from backend.app.ai.base import KINDS, AIResult
from backend.app.ai.mock import MockProvider
from backend.app.ai.service import run_ai, decide_ai, get_provider
from backend.app.models import Exception as Exc, AIRecommendation, AuditEntry

BUNDLE = {"rule_id": "interest_rate_range", "field": "interest_rate",
          "observed_value": "99.0", "expected": "2-36", "message": "out of band"}


def test_kinds_and_defaults():
    assert set(KINDS) == {"explain", "suggest", "compare", "notes", "classify",
                          "summarize", "generate_rule"}
    assert AIResult(kind="explain", text="hi").confidence == 0.0


def test_mock_is_deterministic_and_grounded():
    p = MockProvider()
    assert p.explain(BUNDLE).text == p.explain(BUNDLE).text
    assert "interest_rate" in p.explain(BUNDLE).text and p.explain(BUNDLE).provider == "mock"
    assert p.suggest(BUNDLE).suggested_value is not None
    assert p.compare({**BUNDLE, "sibling_value": "200"}).suggested_value == "200"
    assert p.classify(BUNDLE).suggested_value == "medium"


def test_get_provider_defaults_to_mock():
    assert isinstance(get_provider(), MockProvider)


@pytest.mark.asyncio
async def test_run_ai_persists_and_audits(db):
    e = await Exc(loan_id="LN1", dataset_id="D1", rule_id="interest_rate_range", type="ROW",
                  severity="medium", source="rule", field="interest_rate",
                  observed_value="99.0", expected="2-36", message="x", status="open").insert()
    rec = await run_ai(str(e.id), "suggest", "rev")
    assert rec.provider == "mock" and rec.suggested_value is not None and rec.decision == "pending"
    assert (await Exc.get(e.id)).ai_recommendation_id == str(rec.id)
    assert await AuditEntry.find(AuditEntry.event_type == "ai_recommendation_generated").count() == 1
    rec2 = await decide_ai(str(rec.id), "rejected", "rev")
    assert rec2.decision == "rejected"


@pytest.mark.asyncio
async def test_ai_endpoints(client, db, reviewer_headers, consumer_headers):
    e = await Exc(loan_id="LN1", dataset_id="D1", rule_id="valid_state_code", type="ROW",
                  severity="medium", source="rule", field="borrower_state",
                  observed_value="ZZ", expected="valid US code", message="x", status="open").insert()
    r = await client.post(f"/exceptions/{e.id}/ai", json={"kind": "explain"}, headers=reviewer_headers)
    assert r.status_code == 200 and r.json()["response"]
    rec_id = r.json()["_id"] if "_id" in r.json() else None
    # consumer cannot
    r2 = await client.post(f"/exceptions/{e.id}/ai", json={"kind": "explain"}, headers=consumer_headers)
    assert r2.status_code == 403


@pytest.mark.asyncio
async def test_claude_fallback_to_mock(db, monkeypatch):
    from backend.app.config import get_settings
    get_settings.cache_clear()
    monkeypatch.setenv("LVC_ANTHROPIC_API_KEY", "sk-test")
    from backend.app.ai.claude import ClaudeProvider

    def boom(self, system, user):
        raise RuntimeError("network down")
    monkeypatch.setattr(ClaudeProvider, "_message", boom)

    e = await Exc(loan_id="LN1", dataset_id="D1", rule_id="interest_rate_range", type="ROW",
                  severity="medium", source="rule", field="interest_rate",
                  observed_value="99.0", expected="2-36", message="x", status="open").insert()
    rec = await run_ai(str(e.id), "explain", "rev")
    assert rec.provider == "mock (claude-fallback)" and rec.response
    get_settings.cache_clear()
