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
  observed_value, expected, status (open|resolved|accepted|rejected),
  ai_recommendation_id?, resolution: {action, old_value, new_value, by, at}}`.
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

---

## 7. Module B — Validation Engine

Rules are **data-driven** from `validation_rules.json` (configurable, as the doc
requires) and executed by a modular rule runner. Each rule is a small pure
function `(loan, context) -> Exception | None`. Context carries cross-record and
cross-file state (duplicate index, servicer_update join, document_manifest join).

Rules cover all §7 intentional issues:

| Rule | Detects |
|---|---|
| required_fields | Missing loan_id / required fields |
| valid_dates | Invalid/unparseable date formats |
| maturity_after_origination | maturity_date < origination_date |
| non_negative_amounts | Negative principal or balance |
| balance_le_principal | current_balance > original_principal |
| interest_rate_range | Rate outside expected band (from rules json) |
| payment_status_vs_dpd | payment_status inconsistent with days_past_due |
| closed_with_balance | Loan closed but positive balance |
| document_status_present | Missing document_status / not in manifest |
| valid_state_code | Invalid US state code |
| duplicate_loan_id | Duplicate loan IDs |
| duplicate_borrower_combo | Duplicate borrower + amount + origination_date |
| suspicious_borrower_repeat | Suspiciously repeated borrower records |
| stale_record | last_updated_at older than threshold |
| source_conflict | Conflicting values vs servicer_update.csv |

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

## 12. Phase 2 (differentiator, non-blocking) — ML anomaly layer

After A–H work end-to-end: an unsupervised **Isolation Forest** over numeric
features (principal, balance, rate, term, dpd) plus per-column IQR outlier
detection, trained on the uploaded tape itself. Produces `source=ml` exceptions
for "valid but statistically weird" values the fixed rules can't express.
Clearly labeled in the UI as ML-flagged, low default severity, always reviewer-
gated.

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
  README.md
  docs/
    specs/                 # this file
    architecture-note.md
    ai-development-log.md
  data/                    # synthetic package (generated)
    loan_tape.csv  servicer_update.csv  document_manifest.csv
    validation_rules.json  users.json  expected_exception_sample.csv
  backend/
    app/
      main.py  config.py  db.py  auth.py
      models/              # beanie documents
      schemas/             # pydantic API models
      ingestion/           # parse, normalize, lineage
      validation/          # rule runner + individual rules
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
