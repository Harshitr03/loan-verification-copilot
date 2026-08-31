# P4 — AI Review Assistant (Module D) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the human-in-the-loop AI assistant — one `AIProvider` interface with a deterministic `MockProvider` (works offline, is the test path) and a `ClaudeProvider` (real API when a key is set) — exposing the 7 AI operations, persisting every call to `ai_recommendations` + the audit chain, and recording accept/edit/reject decisions. AI output is rendered separately and never auto-applied.

**Architecture:** `backend/app/ai/{base,mock,claude,service}.py`. `get_provider()` returns Claude when `ANTHROPIC_API_KEY` is set else Mock. The AI service grounds prompts on the shared exception bundle (`{rule_id, field, observed_value, expected, sibling_value?, message}`), persists an `AIRecommendation`, and audits. Endpoints in `backend/app/api/ai.py`.

**Tech Stack:** `anthropic` SDK (model `claude-sonnet-5`), P1 audit + models, P3 exceptions.

**Spec:** parent §2 (AI provider abstraction), §8 (Module D — 7 ops), §9 (AI controls: separate render, never auto-applied, full metadata). Depends on **P3 green**. Roadmap P4.

## Global Constraints

- **Two providers, one interface (spec §2):** `MockProvider` is deterministic (no key needed) and is the default + the test path; `ClaudeProvider` is selected only when `settings.anthropic_api_key` is set. Model id **`claude-sonnet-5`**.
- **Runtime fallback (finding #8):** if the selected `ClaudeProvider` raises (API error/timeout/rate-limit), the AI **service falls back to `MockProvider`** for that call and records `provider="mock (claude-fallback)"` — a flaky network never breaks the demo, and the reviewer still gets a grounded suggestion.
- **Every AI call is recorded (spec §9):** `{provider, model, prompt, response, timestamp}` → an `AIRecommendation` row + an audit `ai_recommendation_generated` event.
- **Never auto-applied:** the AI never mutates a loan/exception. Applying a suggestion happens only through P3's reviewer `resolve` edit path; the AI decision (`accepted|edited|rejected`) is a separate record.
- **The 7 operations (spec §8):** explain, suggest (value+confidence), compare (loan_tape vs servicer_update), notes, classify (severity), summarize (batch), generate_rule (candidate `validation_rules.json` entry, reviewer-approved before effect).
- **Grounding = the bundle, not raw PII:** prompts are built from the exception bundle + minimal loan context (spec §7 "minimal LLM grounding").

---

## File Structure

```
backend/app/ai/
  __init__.py
  base.py           # AIProvider ABC + AIResult dataclass + KINDS
  mock.py           # MockProvider (deterministic templates)
  claude.py         # ClaudeProvider (anthropic SDK, claude-sonnet-5)
  service.py        # get_provider(), run_ai(exception_id, kind) persistence + audit
backend/app/api/ai.py    # POST /exceptions/:id/ai, POST /ai/:id/decision, POST /ai/summarize, POST /ai/generate-rule
backend/tests/
  test_ai_mock.py  test_ai_service.py  test_ai_api.py  test_ai_claude.py
```

Add `anthropic>=0.39` to the `backend` optional-deps group.

---

### Task 1: `AIProvider` interface + `AIResult`

**Files:** Create `backend/app/ai/__init__.py`, `backend/app/ai/base.py`; Test `backend/tests/test_ai_mock.py` (interface part).

**Interfaces:** Produces `KINDS = ("explain","suggest","compare","notes","classify","summarize","generate_rule")`; `@dataclass AIResult{kind:str, text:str, suggested_value:str|None=None, confidence:float=0.0, provider:str="", model:str="", prompt:str=""}`; ABC `AIProvider` with `explain(bundle)`, `suggest(bundle)`, `compare(bundle)`, `notes(bundle)`, `classify(bundle)`, `summarize(bundles)`, `generate_rule(nl_text)` — all returning `AIResult`. `bundle` = a dict with the exception fields + optional loan context.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_ai_mock.py
from backend.app.ai.base import AIProvider, AIResult, KINDS


def test_kinds_are_the_seven_ops():
    assert set(KINDS) == {"explain", "suggest", "compare", "notes", "classify",
                          "summarize", "generate_rule"}


def test_ai_result_defaults():
    r = AIResult(kind="explain", text="hi")
    assert r.suggested_value is None and r.confidence == 0.0
```

- [ ] **Step 2: Run fail.** - [ ] **Step 3: Implement** `base.py` (ABC + dataclass + KINDS). - [ ] **Step 4: Run pass.** - [ ] **Step 5: Commit** `feat(ai): provider interface + AIResult`.

---

### Task 2: `MockProvider` — deterministic templated outputs

**Files:** Create `backend/app/ai/mock.py`; Test extends `backend/tests/test_ai_mock.py`.

**Interfaces:** `MockProvider(AIProvider)` — deterministic per bundle. Examples: `explain` → templated reason referencing `rule_id`/`field`/`observed_value`/`expected`; `suggest` → a concrete `suggested_value` derived from the rule (e.g. `interest_rate_range` → clamp into band midpoint; `valid_state_code` → `"CA"`; `balance_le_principal` → the principal) with `confidence` fixed per rule; `compare` → picks `sibling_value` when present; `classify` → maps rule→severity; `summarize` → counts by rule; `generate_rule` → a JSON stub entry. `provider="mock"`, `model="mock-1"`.

- [ ] **Step 1: Write the failing test**

```python
# add to backend/tests/test_ai_mock.py
from backend.app.ai.mock import MockProvider

BUNDLE = {"rule_id": "interest_rate_range", "field": "interest_rate",
          "observed_value": "99.0", "expected": "2-36", "message": "out of band"}


def test_mock_is_deterministic_and_grounded():
    p = MockProvider()
    a, b = p.explain(BUNDLE), p.explain(BUNDLE)
    assert a.text == b.text and "interest_rate" in a.text and a.provider == "mock"


def test_mock_suggest_returns_value_in_band():
    r = MockProvider().suggest(BUNDLE)
    assert r.suggested_value is not None and 0 < r.confidence <= 1


def test_mock_compare_prefers_sibling():
    r = MockProvider().compare({**BUNDLE, "rule_id": "source_conflict",
                                "field": "current_balance", "observed_value": "100",
                                "sibling_value": "200"})
    assert r.suggested_value == "200"
```

- [ ] **Step 2: Run fail.** - [ ] **Step 3: Implement** `mock.py` with a per-rule template table + deterministic suggestion logic. - [ ] **Step 4: Run pass.** - [ ] **Step 5: Commit** `feat(ai): deterministic MockProvider`.

---

### Task 3: `get_provider()` + `run_ai` service (persist + audit)

**Files:** Create `backend/app/ai/service.py`; Test `backend/tests/test_ai_service.py`.

**Interfaces:** Produces `get_provider() -> AIProvider` (Claude if key else Mock); `async run_ai(exception_id, kind, actor) -> AIRecommendation` — loads the exception, builds the bundle, dispatches to the provider method **wrapped so any provider exception falls back to `MockProvider`** (finding #8; the persisted `provider` records the fallback), persists an `AIRecommendation` (`kind, provider, model, prompt, response, suggested_value, confidence, decision="pending", created_at`), links `exception.ai_recommendation_id`, audits `ai_recommendation_generated`; `async decide_ai(rec_id, decision, actor)` (`accepted|edited|rejected`) updates the row + audits.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_ai_service.py
import pytest
from backend.app.models import Exception as Exc, AIRecommendation, AuditEntry
from backend.app.ai.service import run_ai, decide_ai, get_provider
from backend.app.ai.mock import MockProvider


@pytest.mark.asyncio
async def test_run_ai_persists_and_audits(db, monkeypatch):
    e = await Exc(loan_id="LN1", dataset_id="D1", rule_id="interest_rate_range", type="ROW",
                  severity="medium", source="rule", field="interest_rate",
                  observed_value="99.0", expected="2-36", message="x", status="open").insert()
    rec = await run_ai(str(e.id), "suggest", "rev")
    assert rec.provider == "mock" and rec.suggested_value is not None and rec.decision == "pending"
    assert (await Exc.get(e.id)).ai_recommendation_id == str(rec.id)
    assert await AuditEntry.find(AuditEntry.event_type == "ai_recommendation_generated").count() == 1
    rec2 = await decide_ai(str(rec.id), "rejected", "rev")
    assert rec2.decision == "rejected"


def test_get_provider_defaults_to_mock(monkeypatch):
    assert isinstance(get_provider(), MockProvider)   # no ANTHROPIC key in test env
```

- [ ] **Step 2: Run fail.** - [ ] **Step 3: Implement** `service.py`. - [ ] **Step 4: Run pass.** - [ ] **Step 5: Commit** `feat(ai): AI service — run + persist + audit + decide`.

---

### Task 4: AI endpoints

**Files:** Create `backend/app/api/ai.py`; mount in `main`; Test `backend/tests/test_ai_api.py`.

**Interfaces:** `POST /exceptions/:id/ai {kind}` (reviewer) → the `AIRecommendation`; `POST /ai/:id/decision {decision}` (reviewer); `POST /ai/summarize {dataset_id}` → batch summary; `POST /ai/generate-rule {text}` → candidate rule entry (persisted as pending, not activated).

- [ ] **Step 1: Write the failing test** — reviewer requests `explain` on an exception → 200 + recommendation body; posts `rejected` decision → 200; consumer role → 403.
- [ ] **Step 2: Run fail.** - [ ] **Step 3: Implement** router (reuse `run_ai`/`decide_ai`; summarize/generate_rule call provider directly and persist). - [ ] **Step 4: Run pass.** - [ ] **Step 5: Commit** `feat(api): AI assistant endpoints`.

---

### Task 5: Remaining ops — notes, classify, summarize, generate_rule

**Files:** Modify `backend/app/ai/mock.py` (+ base already declares them); Test extends `test_ai_mock.py`.

**Interfaces:** flesh out `notes` (reviewer-note template), `classify` (rule→severity map), `summarize` (Counter over bundles → text + per-rule counts), `generate_rule` (parse NL → a `{id, params, enabled:false}` candidate JSON string). `generate_rule` output is a **candidate only** — persisted with `decision="pending"`, never merged into `validation_rules.json` without reviewer approval (§8.7).

- [ ] Standard TDD per op; assert determinism + grounding. Commit `feat(ai): notes/classify/summarize/generate_rule ops`.

---

### Task 6: `ClaudeProvider` (real API, key-gated)

**Files:** Create `backend/app/ai/claude.py`; Test `backend/tests/test_ai_claude.py`.

**Interfaces:** `ClaudeProvider(AIProvider)` using `anthropic.Anthropic(api_key=...)`, model `claude-sonnet-5`; each op builds a system+user prompt from the bundle and parses the response into `AIResult` (`provider="claude"`, `model="claude-sonnet-5"`). Network calls are **mocked** in tests (no live key in CI).

- [ ] **Step 1: Write the failing test** — monkeypatch the anthropic client to return a canned message; assert `explain` maps it into `AIResult(text=..., provider="claude", model="claude-sonnet-5")`; assert `get_provider()` returns `ClaudeProvider` when `LVC_ANTHROPIC_API_KEY` is set (monkeypatched settings); **add a fallback test** — make `_message` raise, call `run_ai`, assert the persisted recommendation has `provider="mock (claude-fallback)"` and still carries a grounded suggestion.
- [ ] **Step 2: Run fail.** - [ ] **Step 3: Implement** `claude.py` with a thin `_message(system, user) -> str` seam the test monkeypatches; wire the try/except fallback in `run_ai`. - [ ] **Step 4: Run pass.** - [ ] **Step 5: Commit** `feat(ai): ClaudeProvider (claude-sonnet-5) + runtime Mock fallback`.

Reference the `claude-api` skill for current SDK/model-id usage when implementing the live call.

---

## Self-Review

**1. Spec coverage:** §2 provider abstraction + auto-select + per-call metadata → T1,T3,T6; §8 all 7 ops → T2 (explain/suggest/compare) + T5 (notes/classify/summarize/generate_rule); §8 "separate render, never auto-applied, decision recorded" → T3 (`decision`), never mutates loan; §8.7 generate_rule reviewer-gated → T5; §9 audit `ai_recommendation_generated` → T3. §11 `POST /exceptions/:id/ai` → T4.

**Review fixes folded in:** #8 (Claude→Mock runtime fallback) → constraints + T3 + T6 fallback test; #9 (generate_rule is candidate-only, reviewer-gated before activation) → T5, documented as an intentional demo limitation (the approval→activation loop is not wired; the candidate is persisted `pending`).

**2. Placeholder scan:** each op's deterministic behavior is specified; `KINDS` fixed; claude live call isolated behind a mockable `_message` seam. No TODO.

**3. Type/name consistency:** `AIResult`/`AIProvider`/`KINDS` (T1) used by mock (T2,T5), claude (T6), service (T3); `run_ai`/`decide_ai`/`get_provider` (T3) consumed by API (T4) and P6 UI; `AIRecommendation` fields match P1 §5 model.

## Notes for the executor
- **≥2 rejected-AI examples (deliverable §13):** capture two real cases where the reviewer rejects an AI suggestion during dev; they feed P7's `ai-development-log.md`.
- Keep `MockProvider` the CI default; never require a network call in `pytest -q`.
- Applying a suggestion = call P3 `POST /exceptions/:id/resolve {action:"edit"}` with the suggested value; the AI layer only recommends.
