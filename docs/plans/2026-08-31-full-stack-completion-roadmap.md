# Full-Stack Completion — Master Roadmap

> **Not an executable plan.** This is the decomposition + sequencing map for finishing the
> app (brief Modules A, C–H + frontend + packaging + deliverables). It breaks the work into
> **7 subsystem plans**, each of which becomes its own bite-sized TDD plan (like
> `2026-08-29-data-generator.md`) before execution. Read this first; then we detail and
> execute one subsystem plan at a time.

**Spec:** `docs/specs/2026-08-27-loan-verification-copilot-design.md` (parent). Everything
below is that spec's architecture turned into a build order — no new architecture is invented
here.

**Date:** 2026-08-31.

> **Revision (post-review):** the P1–P7 plan docs were revised after a deep review. Load-bearing
> changes — a shared `chain.HashChain` (atomic seq + stable ISO-timestamp hashing, used by both
> the audit and verified-record chains) in P1; lifespan init/seed in P1; **3-file ingestion**
> (loan_tape + servicer_update + document_manifest) so all 15 rules fire; **`row_uid = loan._id`**
> (not `loan_id`) so `duplicate_loan_id` works and the oracle test has **zero carve-outs**; one
> **summary** `validation_executed` audit event for bulk validation (per-action events for
> reviewer decisions); **all public reads owned solely by P5** (P3 = writes + `/loans/:id/history`);
> a real-Mongo integration lane; severity-weighted quality score; OAuth2-form login; Claude→Mock
> runtime fallback. **Where this roadmap's task outlines differ from a P-plan doc, the P-plan doc
> is authoritative.**

---

## 0. Strategic reframe (why this order)

The brief's judging weights (§1) put **70 of 100 points** in surfaces that do not yet exist:
Full-Stack Completeness (20), Frontend/UX (15), AI Feature Quality (15), Demo (10), plus
Traceability (10) which needs the audit chain + verified records. What exists today —
`loan_rules/` (Module B engine), `data/` (test-data generator, *not* a graded module), and
`fnma_sf/` (optional §12.2 stretch) — is high-quality **foundation** worth ~10–15 pts, but the
graded surface is unbuilt.

**Governing principle (spec §12, §1): a demoable end-to-end vertical slice on the graded
`loan_tape` path comes before any depth or any Phase-2 work.** We reach "it runs end to end
and can be demoed" as early as possible, then deepen. Phase-2 (ML §12.1, FNMA panel ingestion
§12.2) stays last and non-blocking — `fnma_sf/` already exists as a library and only needs a
thin ingestion adapter later.

**Reuse, don't rebuild.** `loan_rules` (the 15 rules, `validate_dataset`, `Dataset`,
`Rule.profiles`), `data/_serialize.CANONICAL_COLUMNS`, and `fnma_sf` are import-pure and
already tested. The backend **consumes** them; it never forks or reimplements them. The
`{rule_id, field, observed_value, expected, sibling_value?, message}` bundle shape is shared
verbatim between the generator's ground truth, the `exceptions` collection, and Module D's LLM
grounding (spec §5, §7).

---

## 1. Subsystem plans (the 7 units)

Each row becomes one detailed TDD plan document. "DoD" = the testable deliverable that proves
the plan is done.

| # | Plan | Modules | Depends on | DoD (testable) |
|---|---|---|---|---|
| P1 | Backend foundation + auth + audit + `HashChain` | (infra) + F | — | App boots (lifespan inits+seeds); form `POST /auth/login` returns a role JWT; shared `HashChain` (atomic seq, stable ts) powers `/audit/verify`; tamper breaks it; real-Mongo lane |
| P2 | 3-file ingestion + validation wiring | A + B | P1 | Upload tape+servicer+manifest → `raw_records` + `loans` + `exceptions`; **all 15 rule types**, oracle superset holds with **zero carve-outs**; one summary audit event; severity-weighted score |
| P3 | Exception workflow + verified records | C + E | P2 | Resolve/edit an exception (per-action audit) + `/loans/:id/history`; verify a loan → `verified_records` via the shared `HashChain` (`seq`-ordered `record_hash`/`prev_record_hash`). **Reads are P5's.** |
| P4 | AI review assistant | D | P3 | `AIProvider` interface; `MockProvider` deterministic; 7 AI ops; every call persisted to `ai_recommendations` + audit; accept/edit/reject; `ClaudeProvider` used when key present |
| P5 | Public read API + export | H | P2–P4 | `GET /loans`, `/loans/:id`, `/exceptions`, `/verified-loans`, `/verified-loans/:id`, `/audit/:loanId`, `/summary`, `/verified-loans/export`; contract tests green; OpenAPI at `/docs` |
| P6 | Frontend — 3 role dashboards | G (+ C/D/E UI) | P1–P5 | Login; operator upload+summary; reviewer queue+drawer+AI panel+resolve/verify; consumer verified grid+audit viewer+export; Playwright smoke of the §15 demo flow |
| P7 | Packaging + deliverables | (§13) | P1–P6 | `docker compose up` runs web+api+mongo; `make seed` loads data; README + architecture-note + ai-development-log + sample verified/audit export present |

**Phase 2 (separate, after P1–P7 green, spec §12):** P8 ML anomaly layer (§12.1); P9 FNMA
panel ingestion adapter wiring `fnma_sf` into Module A (§12.2). Both additive, non-blocking.

---

## 2. Dependency DAG & critical path

```
P1 ─┬─> P2 ─┬─> P3 ─┬─> P4 ─┐
    │       │       │       ├─> P5 ─> P6 ─> P7
    └───────┴───────┴───────┘
                    (P5 also needs P2 loans/exceptions, P3 verified, P4 ai)
```

**Critical path to "demoable":** P1 → P2 → P3 → P5 → P6 (API + minimal UI). P4 (AI) can land
in parallel after P3 and before P6's reviewer panel; if time-boxed, ship P6 with the
MockProvider explain/suggest and defer the richer AI ops to a follow-up pass.

---

## 3. Milestones (delivery checkpoints that cut across the plans)

- **M1 — Vertical slice runs (target: earliest demoable).** P1–P3 at MVP depth + P5 read API +
  P6 minimal UI + P7 docker. Scores first points on Full-Stack Completeness, Traceability,
  Backend Architecture, Demo. AI = MockProvider `explain` only.
- **M2 — Depth + AI.** P4 full (7 ops + Claude), full P3 workflow (filter/search/edit/
  request-correction/history), Module A column-mapping + failed-row detail, dashboards polish,
  export, architecture note, AI development log, demo video. Scores AI Feature Quality,
  Frontend/UX, Agentic Coding, remaining Demo.
- **M3 — Phase 2 (differentiators).** P8 ML, P9 FNMA panel ingestion. Only if M1+M2 green.

Within each detailed plan, tasks needed for M1 are marked **[slice]**; deepening tasks are
marked **[depth]** so execution can stop at a runnable milestone.

---

## 4. Per-plan task outlines

> Task-level only. Each becomes a full bite-sized TDD plan (failing test → run → implement →
> pass → commit) when we detail it. Interfaces shown are the load-bearing signatures/endpoints
> later plans consume.

### P1 — Backend foundation + auth + audit chain (Modules infra + F)
**Dirs:** `backend/app/{main,config,db,auth}.py`, `backend/app/models/`, `backend/app/audit/`,
`backend/tests/`. Add `backend` deps to `pyproject.toml` (fastapi, uvicorn, motor, beanie,
pydantic-settings, python-jose[cryptography], passlib[bcrypt], pytest-asyncio, httpx,
mongomock-motor or a test Mongo).

- **T1 [slice]** App + config + `/health`. `config.Settings` (Mongo URI, JWT secret, `ANTHROPIC_API_KEY?`); `main.create_app()`.
- **T2 [slice]** Beanie models for all 8 collections (spec §5): `User, Dataset, RawRecord, Loan, Exception, AIRecommendation, VerifiedRecord, AuditEntry`; `db.init_db()` binds them with indexes (§5).
- **T3 [slice]** Seed: load `data/users.json` into `users` (idempotent); `make seed` extends to backend.
- **T4 [slice]** Auth: `POST /auth/login` (verify bcrypt hash) → JWT with `{sub, role}`; `get_current_user`/`require_role` deps; 3 role fixtures.
- **T5 [slice]** Audit chain: `audit.append(event_type, entity_type, entity_id, actor, payload) -> AuditEntry` computing `entry_hash = sha256(prev_hash + canonical_json(entry_without_hash))`; monotonic `seq`.
- **T6 [slice]** `GET /audit/verify` recomputes the chain → `{ok, broken_at?}`; test: append N, verify ok; mutate one payload, verify breaks.

**Produces:** the Beanie documents, `audit.append(...)`, `require_role(...)`, `canonical_json(...)`, an app factory + async test client. **DoD:** table above.

### P2 — Ingestion + validation wiring (Modules A + B)
**Dirs:** `backend/app/ingestion/{parse,normalize,lineage}.py`, `backend/app/validation/runner.py`, `backend/app/api/datasets.py`.

- **T1 [slice]** `parse.read_csv(bytes, source_system) -> list[dict]` (pandas; every raw row preserved).
- **T2 [slice]** `POST /datasets` (operator): store `Dataset` + `raw_records` verbatim; audit `file_uploaded`.
- **T3 [slice]** `normalize.to_canonical(raw) -> (loan|None, failure_reason?)` — dates→ISO, currency→Decimal, enum canonicalization, state→2-letter (spec §4); the generated `loan_tape.csv` is already canonical so this is near-identity for it, exercised harder by messy inputs.
- **T4 [slice]** Persist `loans` (lifecycle `imported`) with `dataset_id` + `normalized_from_raw_id` lineage; failed rows recorded with reasons; audit `record_imported`.
- **T5 [slice]** `GET /datasets/:id` summary: total/imported/failed + per-row failure reasons + quality_score.
- **T6 [slice]** `validation.runner.validate_dataset_loans(dataset_id)` — build `loan_rules.Dataset` from the dataset's loans (+ servicer_update/manifest siblings if uploaded), run `load_rules(validation_rules.json)`, write `exceptions` (bundle shape + severity from rule), set loan `validation_status`; audit `validation_executed` + `exception_created`.
- **T7 [slice]** `POST /datasets/:id/validate` triggers T6; **oracle test**: upload the generated tape+`validation_rules.json`, validate, assert exceptions ⊇ `ground_truth_exceptions.csv` pairs (reuses the generator's oracle end-to-end).

**Consumes:** P1 models/audit. **Produces:** populated `loans`/`exceptions`, the runner. **DoD:** table above.

### P3 — Exception queue + verified records (Modules C + E)
**Dirs:** `backend/app/api/exceptions.py`, `backend/app/verification/{builder,hashing}.py`, `backend/app/api/verify.py`.

- **T1 [slice]** `GET /exceptions` list + `GET /loans/:id` detail with its exceptions.
- **T2 [depth]** Filter (type/severity/status), search by loan/borrower id, pagination.
- **T3 [slice]** `POST /exceptions/:id/resolve` — action (approve/reject/request-correction/edit), `resolution{action,old,new,by,at}`, allowed-field edit guard; audit `field_edited`/`loan_approved`/`loan_rejected`.
- **T4 [depth]** Per-loan reviewer action history endpoint; comments.
- **T5 [slice]** `verification.builder.build(loan)` → canonical record + source ref + validation result + reviewer decision + AI ref; `hashing.record_hash = sha256(canonical_json)`; chain `prev_record_hash`.
- **T6 [slice]** `POST /loans/:id/verify` (reviewer): loan must be reviewed; write `verified_records`, set loan `verified`; audit `verified_record_created`.

**Consumes:** P1, P2. **Produces:** verified records + resolution workflow. **DoD:** table above.

### P4 — AI review assistant (Module D)
**Dirs:** `backend/app/ai/{base,mock,claude,service}.py`, `backend/app/api/ai.py`. Add `anthropic` dep.

- **T1 [slice]** `AIProvider` ABC: `explain, suggest, compare, notes, classify, summarize, generate_rule`; `AIResult{text, suggested_value?, confidence, provider, model, prompt}`.
- **T2 [slice]** `MockProvider` — deterministic templated outputs keyed off the exception bundle (works offline; makes AI paths testable).
- **T3 [slice]** Provider selection: `ClaudeProvider` when `ANTHROPIC_API_KEY` set else `MockProvider` (spec §2).
- **T4 [slice]** `POST /exceptions/:id/ai` (kind=explain|suggest|compare) → persist `ai_recommendations` (prompt/model/timestamp) + audit `ai_recommendation_generated`; render separate from decision, never auto-applied.
- **T5 [depth]** Remaining kinds: notes, classify, summarize (batch), generate_rule (writes candidate `validation_rules.json` entry, reviewer-approved before effect).
- **T6 [slice]** Decision: `POST /ai/:id/decision` (accepted|edited|rejected) + audit; ≥2 rejected-AI examples captured for the dev log.
- **T7 [depth]** `ClaudeProvider` live call via `anthropic` SDK (model `claude-sonnet-5`), guarded by key; contract test with a recorded/mocked response.

**Consumes:** P1, P3. **Produces:** AI service + recommendations. **DoD:** table above.

### P5 — Public read API + export (Module H)
**Dir:** `backend/app/api/public.py` (+ wire routers in `main`).

- **T1 [slice]** `GET /loans`, `GET /loans/:id`, `GET /exceptions`, `GET /summary` (counts by status/severity, quality score).
- **T2 [slice]** `GET /verified-loans`, `GET /verified-loans/:id`, `GET /audit/:loanId` (that loan's audit slice).
- **T3 [slice]** `GET /verified-loans/export` — CSV/JSON of verified dataset + audit export (spec §13 sample output).
- **T4 [slice]** Contract tests for each endpoint (shape + auth/role gating); OpenAPI at `/docs`.

**Consumes:** P2–P4. **DoD:** table above.

### P6 — Frontend: 3 role dashboards (Module G + C/D/E UI)
**Dirs:** `frontend/` (Vite+React+TS, Tailwind+shadcn, TanStack Query/Table). `frontend/src/{api,auth,lib,pages,components}`.

- **T1 [slice]** Scaffold + Tailwind/shadcn + API client (axios/fetch + JWT) + TanStack Query; login page → role-routed home.
- **T2 [slice]** Operator dashboard: upload widget → `POST /datasets` → `POST /validate`; import history; validation summary; corrections-needed count.
- **T3 [slice]** Reviewer dashboard: exception queue (TanStack Table, virtualized) with filter/search; loan detail drawer.
- **T4 [slice]** Reviewer AI panel: request explain/suggest/compare (rendered separately), accept/edit/reject; resolve actions; verify button.
- **T5 [slice]** Consumer dashboard: verified-records grid, data-quality score, verification history, export button, audit-trail viewer.
- **T6 [depth]** Component tests (queue + AI panel) + Playwright smoke of the §15 demo flow.

**Consumes:** P1–P5 API. **DoD:** table above.

### P7 — Packaging + deliverables (§13)
**Files:** `docker-compose.yml`, `backend/Dockerfile`, `frontend/Dockerfile`, `Makefile`
(up/down/seed/test), `README.md`, `docs/architecture-note.md`, `docs/ai-development-log.md`.

- **T1 [slice]** `docker-compose.yml`: `mongo`, `api` (uvicorn), `web` (vite build/serve); healthchecks; `.env.example`.
- **T2 [slice]** `make up/down/seed/test`; one-command bring-up runs seed then serves.
- **T3 [slice]** README: setup, env vars (incl. `ANTHROPIC_API_KEY` optional → mock), run commands, **seeded test credentials for all 3 roles**.
- **T4 [depth]** `architecture-note.md` (1–2 pp, from spec §17 trade-offs) + `ai-development-log.md` (tools, 5–10 prompts, human-review process, AI-% estimate, ≥2 rejected-AI examples, lessons — assembled from this repo's spec/TDD/review trail).
- **T5 [slice]** Sample output committed/exported: verified loan dataset + audit trail export (spec §13).

**Consumes:** P1–P6. **DoD:** table above.

---

## 5. Deliverables (§13) → plan mapping

| Deliverable | Plan |
|---|---|
| Working app (`docker compose up`) | P7 (T1–T2) atop P1–P6 |
| README + test credentials | P7 T3 |
| Architecture note | P7 T4 |
| AI Development Log | P7 T4 (assembled from existing spec/TDD/review artifacts) |
| Sample verified output + audit export | P5 T3 + P7 T5 |
| Demo video (≤5 min, §15 flow) | user-recorded after P6/P7 (out of code scope) |

---

## 6. Risks & mitigations

- **Async DB testing friction** → standardize on `pytest-asyncio` + a Mongo test instance
  (docker `mongo` service or `mongomock-motor`); decide in P1 T1 and hold it constant.
- **Scope creep in the frontend** → P6 tasks are MVP-first ([slice] before [depth]); TanStack
  Table + shadcn keep the data grid cheap.
- **AI nondeterminism** → MockProvider is the default and the test path; Claude is behind a key
  and a recorded-response contract test (P4 T7).
- **Sequencing regression** → do **not** start P8/P9 (Phase 2) until P1–P7 are green (spec §12).
- **Double-sourcing rules** → backend imports `loan_rules`; it must never redefine a rule
  (import-purity guard extends to backend in P2).

---

## 7. How we proceed

Each subsystem plan gets written to `docs/plans/2026-08-31-<subsystem>.md` at full bite-sized
TDD granularity (failing test → run → implement → pass → commit), self-reviewed against the
spec, then executed with per-task checkpoints — the same loop already used for the generator
and connector plans. **P1 is the unblocker; it should be detailed and executed first.**
