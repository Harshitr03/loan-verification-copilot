# Loan Data Verification Copilot — Design Spec

**Project:** Intain Campus FinTech Challenge 2026 — Full Stack Track
**Date:** 2026-08-27
**Status:** Draft for review

---

## 1. Goal

Build an AI-assisted full-stack console that ingests messy loan tapes, detects
data-quality issues with a deterministic validation engine, uses an LLM to
explain and help resolve exceptions under human control, and produces
traceable, hash-verified loan records with a complete audit trail.

This spec is scoped to satisfy every graded module (A–H) and deliverable in the
problem statement. It maps each requirement to a concrete component so nothing
graded is left implicit.

### Judging weights (what we optimize for)

| Category | Pts | Where we earn it |
|---|---|---|
| Full-Stack Product Completeness | 20 | End-to-end demo, all modules runnable via `docker compose up` |
| Backend Architecture & Data Modeling | 15 | Modular validation engine, clean Mongo schema, lifecycle, error handling |
| Frontend Workflow & UX | 15 | Three role dashboards, exception queue, AI panel, audit viewer |
| AI Feature Quality | 15 | Module D LLM workflow, visible + logged + human-controlled |
| Agentic Coding Demonstration | 15 | AI Development Log maintained from day one |
| Traceability & Auditability | 10 | Raw→verified lineage, hash-chained audit log, record hashing |
| Demo Quality | 10 | Scripted 5-minute walkthrough, honest limitations |

**Design consequence:** the required modules come first. The ML anomaly model is
a labeled Phase-2 differentiator and must not block A–H.

---

## 2. Tech stack

| Layer | Choice | Reason |
|---|---|---|
| Backend | Python 3.12 + FastAPI | Best-in-class for CSV wrangling, validation, and data work; auto OpenAPI docs |
| Data libs | pandas, pydantic v2 | Parsing/normalization + typed canonical schema |
| Database | MongoDB (Motor async driver) | Flexible raw-record staging + JSON-native audit/verified docs |
| ODM | Beanie (Pydantic-based ODM over Motor) | Typed models, clean lifecycle |
| Frontend | React + Vite + TypeScript | Fast, standard, strong ecosystem |
| UI | Tailwind CSS + shadcn/ui + TanStack Table/Query | Data-dense fintech UI, virtualized grid |
| AI | Anthropic Claude (`claude-sonnet-5`) with a **mock provider fallback** | Required Module D; mock mode = zero-key demo |
| ML (Phase 2) | scikit-learn (Isolation Forest + IQR) | Secondary anomaly layer |
| Auth | JWT with role claim (seeded from `users.json`) | Simple, demo-appropriate; prod-grade security is out of scope |
| Packaging | Docker + docker-compose | One-command run: `web`, `api`, `mongo` |

### AI provider abstraction

A single `AIProvider` interface with two implementations:
- `ClaudeProvider` — real Anthropic API when `ANTHROPIC_API_KEY` is set.
- `MockProvider` — deterministic templated responses so the entire app works
  offline. Selected automatically when no key is present.

Every AI call records `{provider, model, prompt, response, timestamp}` for the
audit trail (§9 AI controls).

---

## 3. Roles (exact)

| Role | Home dashboard | Can do |
|---|---|---|
| **Data Operator** | Upload, import history, validation summary, corrections needed | Upload files, trigger validation, view import lineage |
| **Reviewer** | Exception queue, AI panel, pending & recent decisions | Review exceptions, use AI, edit allowed fields, approve/reject/request-correction, verify records |
| **Data Consumer** | Verified records, data-quality score, verification history, export + audit | Read verified data, inspect audit trail, export, hit the API |

Seeded test credentials for all three roles ship in `users.json` and the README.

---

## 4. Canonical loan schema

From problem statement §6. Normalized internal representation:

```
loan_id (str, required)          borrower_id (str, required)
loan_type (enum)                 origination_date (date)
maturity_date (date)             original_principal (decimal)
current_balance (decimal)        interest_rate (decimal, %)
term_months (int)                borrower_state (US state code)
loan_purpose (enum)              credit_grade (enum)
employment_length (str/int)      income_band (enum)
payment_status (enum)            days_past_due (int)
servicer_name (str)              last_payment_date (date)
last_updated_at (datetime)       document_status (enum)
source_system (str)
```

Normalization handles: multiple date formats → ISO; currency strings → decimal;
enum canonicalization (e.g. `FXD`/`Fixed` → `FIXED`); state-name → 2-letter code;
whitespace/case cleanup. Raw values are preserved for lineage.

---

## 5. Data model (MongoDB collections)

- **users** — `{_id, username, password_hash, role, display_name}` (seeded).
- **datasets** — one upload batch. `{_id, filename, file_type, source_system,
  uploaded_by, uploaded_at, row_count, imported_count, failed_count, status,
  column_mapping, quality_score}`.
- **raw_records** — as-ingested, flexible shape. `{_id, dataset_id, row_number,
  raw: {...arbitrary...}, source_file}`.
- **loans** — normalized canonical records. `{_id, loan_id, dataset_id,
  ...canonical fields..., normalized_from_raw_id, validation_status, lifecycle_state}`.
  Lifecycle: `imported → validated → in_review → verified | rejected`.
- **exceptions** — `{_id, loan_id, dataset_id, rule_id, type, severity
  (low|medium|high|critical), source (rule|ml|reconciliation), field, message,
  observed_value, expected, sibling_value?, status (open|resolved|accepted|rejected),
  ai_recommendation_id?, resolution: {action, old_value, new_value, by, at}}`.
  The `{rule_id, field, observed_value, expected, sibling_value?, message}` subset is
  exactly the **defect context bundle** from the data-generator spec (§7) — one shape
  shared by the generator's ground truth, this record, and Module D's LLM grounding.
  `sibling_value` holds the servicer_update value for `source_conflict`. There is no
  `corrupted_value` field (that is generator-only; the engine has no "before").
- **ai_recommendations** — `{_id, exception_id?, loan_id?, kind, provider, model,
  prompt, response, suggested_value?, confidence, created_at, decision
  (pending|accepted|edited|rejected), decided_by, decided_at}`.
- **verified_records** — Module E. `{_id, loan_id, canonical_data, source_file_ref,
  validation_result, reviewer_decision?, ai_recommendation_ref?,
  verified_at, verified_by, record_hash, prev_record_hash?}`.
- **audit_log** — append-only, **hash-chained** (§9). `{_id, seq, event_type,
  entity_type, entity_id, actor, payload, prev_hash, entry_hash, timestamp}`.

Indexes: `loans.loan_id`, `exceptions.{status,severity,type}`,
`audit_log.seq`, `verified_records.loan_id`.

---

## 6. Module A — Data Ingestion

- Upload CSV (loan_tape, servicer_update, document_manifest) with a declared
  `source_system`.
- Parse via pandas; store every row verbatim in `raw_records` (lineage).
- Suggest a column mapping (heuristic + optional LLM assist for odd headers);
  operator confirms.
- Normalize into `loans`; rows that cannot be normalized become **failed import
  rows** surfaced in the upload summary.
- Upload summary: total / imported / failed, with per-row failure reasons.
- Source-file lineage preserved on every loan (`dataset_id`, `raw_record` link).

### 6.1 Source profiles and dataset grain

Every dataset declares a **profile** that fixes its grain and which rules apply:

| Profile | Grain | Key | Source |
|---|---|---|---|
| `loan_tape` | one row = one loan (loan-grain) | `loan_id` | synthetic package (graded) + collapsed real data |
| `sf_performance_panel` | one row = one loan-month | `(loan_id, reporting_period)` | FNMA SF Loan Performance connector (§6.3, optional stretch) |

The graded A–H path is **always `loan_tape`**. The synthetic package remains the
primary, graded source (it carries ground truth; real data has none). The panel
profile is additive and never becomes a co-equal product — there is no separate
loan-month viewer flow.

### 6.2 Two-pass, grain-aware validation (panel sources)

A `loan_tape` upload runs the existing single pass (normalize → the 15 loan-grain
rules → exceptions). A `sf_performance_panel` upload runs **two extra passes
first**, then joins the graded path:

- **Pass 1 — panel-consistency (grain = loan-month).** Runs at ingestion; findings
  surface as **Module A ingestion exceptions on raw rows** (not loan-grain
  exceptions). Checks:
  - `(loan_id, reporting_period)` is unique; no gaps in a loan's monthly sequence.
  - Per loan, **static** fields are constant across its months: `origination_date`,
    `original_principal`, `term_months`, `maturity_date`, `borrower_state`, credit score.
  - `current_balance` (Current Actual UPB) is monotonically non-increasing over months.
  - Plus the **row-local rule subset** (rules whose `profiles` include
    `sf_performance_panel`; see §7).
- **Pass 2 — collapse to loan tape.** Group by loan; keep the row with the **latest
  `reporting_period`** per loan. Latest (not origination-month) is the chosen
  collapse rule because `payment_status`, `days_past_due`, `current_balance` and
  staleness on the latest month carry the real signal; the origination month would
  make every loan look pristine.
- **Pass 3 — loan-grain validation.** Run the existing **15 loan-grain rules,
  unchanged**, on the collapsed tape. This is the graded path; the collapsed tape is
  an ordinary `loan_tape` dataset from here on.

### 6.3 FNMA SF Loan Performance connector (optional stretch)

Parses the headerless, pipe-delimited FNMA Single-Family Loan Performance file
(`source_system = "FNMA_SF_LPD"`) per the CRT glossary. **The file has a leading
pipe**, so after `line.split('|')` glossary field *N* is at `parts[N-1]`
(`parts[0]` is the empty Reference Pool ID) — this off-by-one is load-bearing and is
pinned by a test. Field map (glossary position → canonical field):

| Canonical | Glossary pos | Source field / derivation |
|---|---|---|
| `loan_id` | 2 | Loan Identifier |
| `last_updated_at` | 3 | Monthly Reporting Period (MMYYYY → date, day=01) |
| `servicer_name` | 6 | Servicer Name |
| `interest_rate` | 9 | Current Interest Rate |
| `original_principal` | 10 | Original UPB |
| `current_balance` | 12 | Current Actual UPB |
| `term_months` | 13 | Original Loan Term |
| `origination_date` | 14 | Origination Date (MMYYYY) |
| `maturity_date` | 19 | Maturity Date (MMYYYY) |
| `borrower_state` | 31 | Property State |
| `loan_purpose` | 27 | P→PURCHASE, C→CASHOUT, R→REFI, **U→REFI (unspecified)** |
| `credit_grade` | 24 | Borrower Credit Score (FICO) → A/B/C/D bands |
| `payment_status` | 44,40 | Zero Balance Code (44) present → CLOSED; else delinquency (40): `"00"`→CURRENT, numeric>0→DELINQUENT, `"XX"`→null |
| `days_past_due` | 40 | numeric months × 30; `"XX"` → null |
| `last_payment_date` | 51 | Last Paid Installment Date (MMYYYY) |
| `source_system` | — | `"FNMA_SF_LPD"` |
| `borrower_id`, `income_band`, `document_status` | — | no source → null (flow into failed/partial-import surface, must not crash normalization) |

MMYYYY dates are month-precision (day=01). Positions are verified against
`crt-file-layout-and-glossary.xlsx`.

---

## 7. Module B — Validation Engine

Rules are **data-driven** from `validation_rules.json` (configurable, as the doc
requires) and executed by a modular rule runner. Each rule is a self-describing
**`Rule` object** — the shared spine defined in the standalone `loan_rules`
package (see the [data-generator spec](./2026-08-29-data-generator-design.md) §3) —
carrying `id`, `scope`, `severity`, `params`, `message_tmpl`, `profiles`, and two
pure functions that take `params` explicitly: `check` (detect) and `corrupt`
(manufacture, used only by the generator). The engine imports these rules and calls
`.check`; the generator imports the same objects and calls `.corrupt`, so injection
and detection can never drift.

**`profiles: frozenset[str]`** declares which dataset profiles (§6.1) a rule applies
to — `{"loan_tape"}`, or `{"loan_tape", "sf_performance_panel"}`. The runner filters
rules by the dataset's profile, so panel-grain passes only run rules that are
meaningful loan-month by loan-month. Identity/time rules
(`duplicate_loan_id`, `duplicate_borrower_combo`, `suspicious_borrower_repeat`,
`stale_record`, `source_conflict`) are **`loan_tape`-only**: at panel grain the key is
`(loan_id, period)`, so e.g. `duplicate_loan_id` would flag every loan ~125×.
`required_fields` and `document_status_present` are also `loan_tape`-only — they
reference fields the panel connector leaves null (`borrower_id`, `document_status`),
which the panel pass instead surfaces through Module A's partial-import row (§6.2).

Rules are **`ROW`- or `DATASET`-scoped**. `ROW` rules judge one loan in isolation
(`check(loan, params) -> Exception | None`). `DATASET` rules
(`duplicate_loan_id`, `duplicate_borrower_combo`, `suspicious_borrower_repeat`,
`source_conflict`, `document_status_present`) need cross-record/cross-file context —
`check(dataset, ctx, params) -> list[Exception]` — where `ctx` carries the duplicate
index, servicer_update join, and document_manifest join.

Rules cover all §7 intentional issues:

Profiles: **B** = both (`loan_tape` + `sf_performance_panel`, row-local); **T** =
`loan_tape` only.

| Rule | Detects | Profiles |
|---|---|---|
| required_fields | Missing loan_id / required fields | T |
| valid_dates | Invalid/unparseable date formats | B |
| maturity_after_origination | maturity_date < origination_date | B |
| non_negative_amounts | Negative principal or balance | B |
| balance_le_principal | current_balance > original_principal | B |
| interest_rate_range | Rate outside expected band (from rules json) | B |
| payment_status_vs_dpd | payment_status inconsistent with days_past_due | B |
| closed_with_balance | Loan closed but positive balance | B |
| document_status_present | Missing document_status / not in manifest | T |
| valid_state_code | Invalid US state code | B |
| duplicate_loan_id | Duplicate loan IDs | T |
| duplicate_borrower_combo | Duplicate borrower + amount + origination_date | T |
| suspicious_borrower_repeat | Suspiciously repeated borrower records | T |
| stale_record | last_updated_at older than threshold | T |
| source_conflict | Conflicting values vs servicer_update.csv | T |

The 8 **B** rules are the row-local subset Pass 1 (§6.2) reuses on panel rows; the 7
**T** rules run only on the collapsed loan tape (Pass 3).

Output: exceptions with type + severity + provenance; per-dataset **data-quality
score** = f(exception counts weighted by severity).

---

## 8. Modules C & D — Exception Queue + AI Review Assistant

**Module C (Reviewer UI):** list/filter exceptions by type & severity, search by
loan/borrower id, open loan detail, add comments, approve / reject / request
correction, edit allowed fields, and a per-loan reviewer action history.

**Module D (AI, all human-in-the-loop):**
1. Explain why a record failed validation.
2. Suggest likely corrections (with a concrete suggested value + confidence).
3. Compare conflicting records (loan_tape vs servicer_update) and recommend the
   reliable value.
4. Generate reviewer notes.
5. Classify exception severity.
6. Summarize a batch of exceptions.
7. Generate validation rules/tests from natural language (writes a candidate
   entry for `validation_rules.json`, reviewer approves before it takes effect).

All AI output is rendered **separately** from the human decision, is never
auto-applied, and every suggestion + its accept/edit/reject decision is written
to `ai_recommendations` and the audit log with prompt/model/timestamp metadata.

---

## 9. Modules E & F — Verified Records + Audit Trail (traceability)

**Verified record (E):** on reviewer verification, assemble the canonical record
+ source ref + validation result + reviewer decision + AI ref (if used) +
timestamp + verified-by, compute `record_hash = sha256(canonical_json(record))`,
and persist.

**Audit trail (F):** every graded event — file uploaded, record imported,
validation executed, exception created, AI recommendation generated, comment
added, field edited, loan approved/rejected, verified record created, verified
record exported — appends one entry. Integrity via **hash chain**:

```
entry_hash = sha256(prev_hash + canonical_json(entry_without_hash))
```

Any tampering breaks the chain; a `/audit/verify` check can prove integrity end
to end. This is how we earn Traceability points without real blockchain (which is
explicitly out of scope).

---

## 10. Module G — Dashboards

- **Data Operator:** upload widget, import history table, validation summary,
  "corrections needed" count.
- **Reviewer:** exception queue, AI assistant panel, pending decisions, recent
  decisions.
- **Data Consumer:** verified records grid, data-quality score, verification
  history, export button + audit trail viewer.

---

## 11. Module H — Verified Records API

Exact endpoints (public read API, plus the internal workflow endpoints):

```
GET /loans                 GET /loans/:id
GET /exceptions            GET /verified-loans
GET /verified-loans/:id    GET /audit/:loanId
GET /summary
```

Workflow/auth endpoints (internal): `POST /auth/login`,
`POST /datasets` (upload), `POST /datasets/:id/validate`,
`POST /exceptions/:id/ai` (explain/suggest/compare), `POST /exceptions/:id/resolve`,
`POST /loans/:id/verify`, `GET /verified-loans/export`. FastAPI auto-serves
OpenAPI docs at `/docs`.

---

## 12. Phase 2 (differentiators, non-blocking)

Both are additive stretch work, started only after A–H run end-to-end on the graded
synthetic `loan_tape` path.

### 12.1 ML anomaly layer

An unsupervised **Isolation Forest** over numeric features (principal, balance,
rate, term, dpd) plus per-column IQR outlier detection, trained on the uploaded tape
itself. Produces `source=ml` exceptions for "valid but statistically weird" values
the fixed rules can't express. Clearly labeled in the UI as ML-flagged, low default
severity, always reviewer-gated.

### 12.2 Real-data connector — FNMA SF Loan Performance

The `sf_performance_panel` connector and two-pass grain-aware pipeline (§6.1–6.3).
Ingests the real FNMA Single-Family Loan Performance file, validates it at loan-month
grain (Pass 1), collapses to the latest month per loan (Pass 2), and feeds the
collapsed tape into the **unchanged** 15 loan-grain rules (Pass 3). This proves the
engine against externally-sourced data — but real data carries **no ground truth**,
so the synthetic package stays the graded oracle; the connector is stretch, never the
primary source. The demo collapses a 5,000-loan slice from the quarterly file. Raw
FNMA files are git-ignored (large / licensed); only a small collapsed fixture from the
8-loan sample is committed for tests.

---

## 13. Deliverables checklist (§12)

- [ ] GitHub repository, complete source.
- [ ] Working app: `docker compose up` local run (+ optional hosted — user owns deploy).
- [ ] README: setup, env vars, run commands, test credentials.
- [ ] Demo video ≤ 5 min (script follows §15 flow).
- [ ] Architecture note (1–2 pages) — derived from this spec.
- [ ] **AI Development Log** — maintained continuously: tools, 5–10 prompts,
      human-review process, AI-code % estimate, ≥2 rejected-AI examples, lessons.
- [ ] Test credentials for all three roles.
- [ ] Sample output: verified loan dataset + audit trail export.

---

## 14. Repository layout

```
loan-verification-copilot/
  docker-compose.yml
  Makefile                 # up, down, seed, test
  pyproject.toml           # editable install of loan_rules (shared by backend + generator)
  README.md
  docs/
    specs/                 # this file + data-generator spec
    architecture-note.md
    ai-development-log.md
  loan_rules/              # STANDALONE shared spine — Rule objects (check + corrupt),
                           # import-pure (no Beanie/Mongo). Imported by both backend
                           # and data/generate.py. NOT under backend/app.
  data/
    generate.py            # seeded synthetic-package generator (imports loan_rules)
    loan_tape.csv  servicer_update.csv  document_manifest.csv          # generated
    validation_rules.json  users.json  expected_exception_sample.csv   # generated
    ground_truth_exceptions.csv                                        # generated test oracle
  backend/
    app/
      main.py  config.py  db.py  auth.py
      models/              # beanie documents
      schemas/             # pydantic API models
      ingestion/           # parse, normalize, lineage
      validation/          # rule runner + context builder (consumes loan_rules)
      ai/                  # AIProvider, ClaudeProvider, MockProvider
      audit/               # hash chain
      verification/        # verified-record builder + hashing
      api/                 # routers (Module H + workflow)
      ml/                  # Phase 2 anomaly layer
    tests/
  frontend/
    src/
      pages/               # operator, reviewer, consumer dashboards
      components/          # grid, exception drawer, AI panel, audit viewer
      api/  lib/  auth/
```

Note: the individual rule *definitions* live in the standalone `loan_rules/`
package (so the generator can import them without standing up the app/DB);
`backend/app/validation/` holds only the runner and the cross-file context builder
that consume them.

---

## 15. Out of scope (per §16)

Real structured-finance analytics, securitization, borrowing-base calc, real OCR,
real blockchain, underwriting, credit scoring, payment workflows, production-grade
security, regulatory compliance. Security is demo-grade JWT only.

---

## 16. Testing strategy

- **Backend:** pytest for the validation engine (one test per rule against known
  fixtures from `expected_exception_sample.csv`), ingestion/normalization, hash
  chain integrity, and API contract tests for Module H.
- **AI:** MockProvider makes AI paths deterministic and testable.
- **Frontend:** component tests for the exception queue and AI panel; a Playwright
  smoke test of the §15 demo flow.
- TDD: write the failing test per rule before implementing it.

---

## 17. Key trade-offs (for the architecture note)

- **Mongo over Postgres:** flexible staging for messy inbound shapes; integrity
  for audit comes from an explicit hash chain rather than FK constraints.
- **Rules-first, ML-second:** deterministic detection is auditable and matches the
  graded issue list; ML is additive, not load-bearing.
- **LLM suggestion-only:** satisfies §9 AI controls; detection stays deterministic.
- **Mock AI fallback:** guarantees a working demo with no external dependency.
- **Synthetic tape is the graded oracle; real data is optional stretch:** the
  synthetic package has ground truth, so it's the only source we can prove the engine
  against. The FNMA connector (§12.2) adds real-data credibility but has no ground
  truth — it validates behavior, not correctness.
- **Grain-aware rules over forking the product:** rather than a separate loan-month
  product, one `profiles` dimension on `Rule` lets the same engine validate panel data
  (Pass 1) and, after a latest-month collapse (Pass 2), reuse the unchanged 15
  loan-grain rules (Pass 3). Changes stay additive; the graded loan-tape path is
  untouched.
- **Collapse to latest month, not origination:** the latest reporting month carries
  the live payment/delinquency/balance signal; origination-month would make every
  loan look pristine and defeat validation.
