# P3 — Exception Queue + Verified Records (Modules C + E) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give reviewers the exception-queue workflow (list / filter / search / open / resolve / edit allowed fields / per-loan history) and the verified-record path (build canonical record + `record_hash` chained on `prev_record_hash`, flip loan to `verified`), each event audited.

**Architecture:** `backend/app/api/exceptions.py` serves queue + resolve; `backend/app/verification/{builder,hashing}.py` assembles and hashes verified records; `backend/app/api/verify.py` exposes verify. Reuses P1 `audit.append`/`canonical_json` and P2 loans/exceptions.

**Tech Stack:** FastAPI, Beanie queries (filter/sort/paginate), P1 `canonical_json` + audit chain.

**Spec:** parent §8 (Module C), §9 (Module E verified record + hash), §11. Depends on **P2 green**. Roadmap P3.

## Global Constraints

- **Allowed-field edits only:** a reviewer may edit a bounded set of loan fields (`ALLOWED_EDIT_FIELDS = {"interest_rate","current_balance","payment_status","days_past_due","borrower_state","loan_purpose","maturity_date","document_status"}`); edits outside it are 422. Every edit records `{old,new,by,at}` and audits `field_edited`.
- **Verified-record chain via the shared `HashChain` (spec §9, finding 1c):** use `HashChain(VerifiedRecord, "verified", prev_field="prev_record_hash", hash_field="record_hash", ts_field="verified_at")` from P1 — it gives the chain a defined `seq` order and the stable `ts_iso` hashing. `canonical_data` is **pre-serialized to strings** (via `data._serialize.format_value`) so the hashed body is BSON-stable (P1's domain-stability rule).
- **Route ownership (finding RC4):** P3 owns **workflow writes only** (`resolve`, `verify`) + the distinctly-shaped `GET /loans/:id/history`. All public **reads** (`GET /exceptions`, `GET /loans/:id`, `/verified-loans*`, `/summary`, `/audit/:loanId`) live in **P5**. P3's tests seed via models directly, so they need no read routes.
- **Resolution actions:** `approve | reject | request_correction | edit` → exception `status ∈ {resolved, rejected, accepted, open}` per §5; loan `lifecycle_state` transitions (`in_review → verified|rejected`).
- **Role gating:** resolve/edit/verify = reviewer only.
- Reuse P1 `audit.append` for every graded **reviewer action** (§9) — these are per-action events (unlike bulk validation's summary event).

---

## File Structure

```
backend/app/
  api/exceptions.py         # POST /exceptions/:id/resolve, GET /loans/:id/history  (writes + history only)
  verification/
    __init__.py
    builder.py              # build_verified_record(loan, reviewer, ai_ref=None) via HashChain
  api/verify.py             # POST /loans/:id/verify
backend/tests/
  test_resolve.py  test_history.py  test_verification.py  test_verify_api.py
```

(Reads — `GET /exceptions`, `GET /loans/:id` — are **P5's**, not here.)

---

### Task 1: Resolve / edit an exception (workflow + audit)

**Files:** Create `backend/app/api/exceptions.py`; mount in `main`; Test `backend/tests/test_resolve.py`.

**Interfaces:** `POST /exceptions/:id/resolve` (reviewer) body `{action, field?, new_value?, note?}` → updated exception. `action=edit` applies an allowed-field edit to the loan (`{old,new,by,at}`), sets exception `status="accepted"`, audits `field_edited`. `approve→resolved`, `reject→rejected`, `request_correction→open` (with note), each audited (`loan_approved`/`loan_rejected`/`comment_added`). Loan `lifecycle_state` → `in_review` on first action.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_resolve.py
import pytest
from decimal import Decimal
from backend.app.models import Loan, Exception as Exc, AuditEntry


@pytest.mark.asyncio
async def test_edit_applies_allowed_field_and_audits(client, db, reviewer_headers):
    await Loan(loan_id="LN1", dataset_id="D1", interest_rate=Decimal("99.0"),
               validation_status="validated").insert()
    e = Exc(loan_id="LN1", dataset_id="D1", rule_id="interest_rate_range", type="ROW",
            severity="medium", source="rule", field="interest_rate", observed_value="99.0",
            expected="2-36", message="x", status="open")
    await e.insert()
    r = await client.post(f"/exceptions/{e.id}/resolve",
                          json={"action": "edit", "field": "interest_rate", "new_value": "5.25"},
                          headers=reviewer_headers)
    assert r.status_code == 200
    loan = await Loan.find_one(Loan.loan_id == "LN1")
    assert loan.interest_rate == Decimal("5.25")
    assert (await Exc.get(e.id)).status == "accepted"
    assert await AuditEntry.find(AuditEntry.event_type == "field_edited").count() == 1


@pytest.mark.asyncio
async def test_edit_rejects_disallowed_field(client, db, reviewer_headers):
    e = await Exc(loan_id="LN1", dataset_id="D1", rule_id="r", type="ROW", severity="low",
                  source="rule", field="loan_id", observed_value="x", expected="y",
                  message="m", status="open").insert()
    r = await client.post(f"/exceptions/{e.id}/resolve",
                          json={"action": "edit", "field": "loan_id", "new_value": "Z"},
                          headers=reviewer_headers)
    assert r.status_code == 422
```

- [ ] **Step 2: Run fail.** - [ ] **Step 3: Implement** resolve handler with `ALLOWED_EDIT_FIELDS`, type coercion for edited value (reuse `ingestion.normalize` helpers for Decimal/date), `resolution` dict, audit calls. - [ ] **Step 4: Run pass.** - [ ] **Step 5: Commit** `feat(api): exception resolve/edit workflow with audit`.

---

### Task 2: Per-loan reviewer history

**Files:** Modify `backend/app/api/exceptions.py`; Test `backend/tests/test_history.py`.

**Interfaces:** `GET /loans/:id/history` → the audit entries for that loan (`entity_type="loan", entity_id=loan_id`) in `seq` order. (This shape is distinct from the public reads, so it stays in P3.)

- [ ] Standard TDD: after an edit + approve, history returns ≥2 ordered entries. Commit `feat(api): per-loan reviewer action history`.

---

### Task 3: Verified-record builder via `HashChain`

**Files:** Create `backend/app/verification/{__init__,builder}.py`; Test `backend/tests/test_verification.py`.

**Interfaces:** Produces `async build_verified_record(loan, reviewer, ai_ref=None) -> VerifiedRecord` — assembles the domain content `{loan_id, canonical_data, source_file_ref, validation_result, reviewer_decision, ai_recommendation_ref, verified_by}` where **`canonical_data` is serialized to strings** via `data._serialize.format_value` (BSON-stable per P1's rule), then appends it through `HashChain(VerifiedRecord, "verified", prev_field="prev_record_hash", hash_field="record_hash", ts_field="verified_at")`. The chain sets `seq`, `record_hash`, `prev_record_hash`, `ts_iso`, `verified_at` — so ordering and hashing are handled once, shared with audit (finding 1c).

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_verification.py
import pytest
from backend.app.models import Loan, VerifiedRecord
from backend.app.verification.builder import build_verified_record
from backend.app.chain import HashChain


@pytest.mark.asyncio
async def test_verified_records_chain_orders_by_seq(db):
    l1 = await Loan(loan_id="LN1", dataset_id="D1", validation_status="validated").insert()
    l2 = await Loan(loan_id="LN2", dataset_id="D1", validation_status="validated").insert()
    v1 = await build_verified_record(l1, "rev")
    v2 = await build_verified_record(l2, "rev")
    assert (v1.seq, v2.seq) == (1, 2)
    assert v1.prev_record_hash == "" and v2.prev_record_hash == v1.record_hash
    # the shared chain's verify() proves integrity + defined order
    chain = HashChain(VerifiedRecord, "verified", prev_field="prev_record_hash",
                      hash_field="record_hash", ts_field="verified_at")
    assert (await chain.verify())["ok"] is True
```

- [ ] **Step 2: Run fail.** - [ ] **Step 3: Implement** `builder.py` calling the shared `HashChain`. - [ ] **Step 4: Run pass.** - [ ] **Step 5: Commit** `feat(verification): verified-record builder over shared HashChain`.

---

### Task 4: `POST /loans/:id/verify`

**Files:** Create `backend/app/api/verify.py`; mount in `main`; Test `backend/tests/test_verify_api.py`.

**Interfaces:** `POST /loans/:id/verify` (reviewer) → builds the verified record, sets loan `lifecycle_state="verified"`, audits `verified_record_created` (per-action event). Guard: loan must be `validated`/`in_review` (not already `verified`).

- [ ] **Step 1: Write the failing test** — reviewer verifies a validated loan → 200, `VerifiedRecord` exists, loan `lifecycle_state=="verified"`, audit has `verified_record_created`; second verify → 409; consumer → 403.
- [ ] **Step 2: Run fail.** - [ ] **Step 3: Implement.** - [ ] **Step 4: Run pass.** - [ ] **Step 5: Commit** `feat(api): loan verify endpoint`.

---

## Self-Review

**1. Spec coverage:** §8 Module C workflow (resolve/edit/approve/reject/request-correction + history) → T1,T2 (list/filter/search reads are P5's); §9 Module E verified record + chain → T3,T4; graded reviewer actions audited per-event → T1,T4. §11 `POST /exceptions/:id/resolve`, `POST /loans/:id/verify` → T1,T4.

**Review fixes folded in:** RC4 (reads moved to P5; P3 = writes + `history` only) → constraints + file structure + task removal; 1c (verified chain has defined `seq` order via shared `HashChain`) → T3; RC1 (reviewer actions are per-event, distinct from bulk validation's summary event) → constraints.

**2. Placeholder scan:** `ALLOWED_EDIT_FIELDS` enumerated; resolve action semantics specified; verified builder delegates hashing to the shared, fully-specified `HashChain`. No TODO.

**3. Type/name consistency:** `build_verified_record` name fixed here, consumed by P4 (ai_ref) + P5 (export) + P6; `resolution` dict shape matches P1 `Exception.resolution`; `HashChain` signature matches P1 T5; audit event names match §9 and are read by P5's `/audit/:loanId`.

## Notes for the executor
- Reuse `ingestion.normalize` coercion helpers when applying an edited `new_value` so an edited Decimal/date is typed consistently with imported values.
- `reviewer_headers`/`consumer_headers`/`operator_headers` come from P1's conftest fixtures.
- The verified chain is a **separate** `HashChain` instance/counter (`name="verified"`) from audit (`name="audit"`) — two independent chains sharing one implementation (spec §9 has both).
