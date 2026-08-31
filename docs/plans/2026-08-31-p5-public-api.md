# P5 — Public Read API + Export (Module H) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Serve the exact Module H read API — `GET /loans`, `/loans/:id`, `/exceptions`, `/verified-loans`, `/verified-loans/:id`, `/audit/:loanId`, `/summary` — plus the verified-dataset + audit **export**, with contract tests and OpenAPI at `/docs`.

**Architecture:** `backend/app/api/public.py` collects the read endpoints (some overlap earlier plans' internal routes; H is the consolidated, role-gated public surface). Export reuses `data._serialize` writers for stable output. No new domain logic — pure read + shape.

**Tech Stack:** FastAPI, Beanie queries, `data._serialize` (CSV writers), P1–P4 collections.

**Spec:** parent §11 (exact endpoints), §13 (sample verified output + audit export). Depends on **P2–P4 green**. Roadmap P5.

## Global Constraints

- **Exact endpoint paths (spec §11):** do not rename. `GET /loans, /loans/:id, /exceptions, /verified-loans, /verified-loans/:id, /audit/:loanId, /summary, /verified-loans/export`.
- **Role gating:** the public read API is available to any authenticated user; `/verified-loans*` + export are the Data Consumer surface but readable by all roles (spec §3 consumer "hit the API"). Write/workflow routes stay in their owning plans.
- **Stable serialization:** exported CSV uses `data._serialize.format_value` + `CANONICAL_COLUMNS` so the sample output is byte-stable and matches the graded tape shape.
- **`/summary`** returns dataset-level + global counts: totals, by-status, by-severity, verified count, quality score.

---

## File Structure

```
backend/app/api/public.py     # all §11 read endpoints + export
backend/tests/
  test_public_reads.py  test_summary.py  test_export.py
```

---

### Task 1: `/loans`, `/loans/:id`, `/exceptions`

**Files:** Create `backend/app/api/public.py`; mount in `main`; Test `backend/tests/test_public_reads.py`.

**Interfaces (P5 is the sole owner of all public reads — finding RC4):** `GET /loans?dataset_id&status&skip&limit` → `{items,total}`; `GET /loans/:id` → `{loan, exceptions}` (the loan **plus its exceptions** — one shape serving both the public read and P6's detail drawer; 404 if absent); `GET /exceptions?status&severity&type&loan_id&q&skip&limit` → `{items,total}` (filter + search, **defined here, not P3**). All require an authenticated user.

- [ ] **Step 1: Write the failing test** — seed 2 loans + exceptions (2 open/high, 1 resolved/low); assert `GET /loans` returns 2; `GET /loans/LN1` returns `{loan, exceptions}`; `GET /loans/NOPE` → 404; `GET /exceptions?severity=high` returns 2; `GET /exceptions?status=resolved` returns 1; unauthenticated → 401.
- [ ] **Step 2: Run fail.** - [ ] **Step 3: Implement** router — includes the `/exceptions` filter+search handler (the one P3 no longer defines; `q` matches loan/borrower id). - [ ] **Step 4: Run pass.** - [ ] **Step 5: Commit** `feat(api): public loans + exceptions reads (sole owner)`.

---

### Task 2: `/verified-loans`, `/verified-loans/:id`, `/audit/:loanId`

**Files:** Modify `backend/app/api/public.py`; Test extends `test_public_reads.py`.

**Interfaces:** `GET /verified-loans` → `{items,total}` of `verified_records`; `GET /verified-loans/:id` → one (by `loan_id`); `GET /audit/:loanId` → that loan's audit entries (`entity_type="loan", entity_id=loanId`) in `seq` order + a `chain_ok` flag from `verify_chain()` scoped/global.

- [ ] **Step 1: Write the failing test** — after verifying a loan (reuse P3 helper) assert `/verified-loans` returns 1, `/verified-loans/LN1` returns it with a `record_hash`, `/audit/LN1` returns ordered entries.
- [ ] **Step 2: Run fail.** - [ ] **Step 3: Implement.** - [ ] **Step 4: Run pass.** - [ ] **Step 5: Commit** `feat(api): verified-loans + per-loan audit reads`.

---

### Task 3: `/summary`

**Files:** Modify `backend/app/api/public.py`; Test `backend/tests/test_summary.py`.

**Interfaces:** `GET /summary` → `{datasets, loans_total, verified_total, exceptions_by_status, exceptions_by_severity, avg_quality_score}` (aggregate counts across collections).

- [ ] **Step 1: Write the failing test** — seed a dataset + loans + exceptions (2 high open, 1 low resolved) + 1 verified; assert the summary buckets match.
- [ ] **Step 2: Run fail.** - [ ] **Step 3: Implement** with count queries (avoid heavy aggregation to stay mongomock-friendly — use `find(...).count()` per bucket). - [ ] **Step 4: Run pass.** - [ ] **Step 5: Commit** `feat(api): summary counts endpoint`.

---

### Task 4: `/verified-loans/export`

**Files:** Modify `backend/app/api/public.py`; Test `backend/tests/test_export.py`.

**Interfaces:** `GET /verified-loans/export?format=csv|json` → a downloadable verified dataset. CSV path writes the canonical 21 columns via `data._serialize` (into an in-memory buffer) for each verified record's `canonical_data`; a companion `GET /audit/export` streams the full audit log (the §13 audit export). Response is `text/csv`/`application/json` with a `Content-Disposition` attachment header.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_export.py
import pytest, csv, io
from data._serialize import CANONICAL_COLUMNS


@pytest.mark.asyncio
async def test_export_csv_has_canonical_header(client, db, reviewer_headers, verified_loan):
    r = await client.get("/verified-loans/export?format=csv", headers=reviewer_headers)
    assert r.status_code == 200 and "text/csv" in r.headers["content-type"]
    rows = list(csv.reader(io.StringIO(r.text)))
    assert rows[0] == CANONICAL_COLUMNS
    assert len(rows) - 1 >= 1                     # at least the verified loan
```

(`verified_loan` fixture verifies one loan via the P3 path.)

- [ ] **Step 2: Run fail.** - [ ] **Step 3: Implement** export using `data._serialize.format_value` per canonical column; audit `verified_record_exported`. - [ ] **Step 4: Run pass.** - [ ] **Step 5: Commit** `feat(api): verified dataset + audit export`.

---

### Task 5: Contract-test sweep + OpenAPI

**Files:** Test `backend/tests/test_public_reads.py` (add).

**Interfaces:** a parametrized test hitting each §11 GET path asserting 200 (authenticated) and 401 (anonymous), and that `GET /openapi.json` lists all §11 paths.

- [ ] Standard TDD. Commit `test(api): Module H contract + OpenAPI coverage`.

---

## Self-Review

**1. Spec coverage:** §11 all 8 endpoints → T1–T4; §13 sample verified output + audit export → T4; OpenAPI `/docs` → FastAPI default + T5 assertion.

**Review fixes folded in:** RC4 (P5 is the **single owner** of every public read — `/loans`, `/loans/:id`, `/exceptions`, `/verified-loans[/:id]`, `/summary`, `/audit/:loanId`; P3 keeps only writes + `/loans/:id/history`) → constraints + T1,T2; `/loans/:id` shape reconciled to `{loan, exceptions}` (serves both public read and the P6 drawer).

**2. Placeholder scan:** every endpoint has an explicit shape + test; export uses named `data._serialize` helpers. No TODO.

**3. Type/name consistency:** reuses `CANONICAL_COLUMNS`/`format_value` (data package), `verify_chain` (P1), P2–P3 collections. Paths copied verbatim from §11. No path is defined in more than one plan (RC4 resolved).

## Notes for the executor
- P3 no longer defines `/exceptions` or `/loans/:id` — they are defined **here** for the first time; there is no duplication to reconcile.
- Keep `/summary` on simple `count()` queries for mongomock compatibility; a real-Mongo aggregation optimization is a later, optional refinement.
