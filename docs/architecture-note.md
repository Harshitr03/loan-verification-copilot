# Architecture Note — Loan Data Verification Copilot

*(1–2 pages; derived from `docs/specs/2026-08-27-loan-verification-copilot-design.md`.)*

## System shape

A three-layer system: **pure shared libraries** → **FastAPI/Beanie backend** → **React SPA**,
with MongoDB for storage.

- **`loan_rules/`** — the 15 validation rules as self-describing `Rule` objects, each carrying a
  pure `check` (detect) and `corrupt` (manufacture a defect), both taking `params` explicitly.
  Import-pure: no DB, no web. This is the technical heart of Module B.
- **`data/`** — a seeded generator that emits an internally-consistent synthetic loan package
  plus a machine-checkable **ground-truth oracle** (every injected defect is recorded). Not a
  graded module; it's how we *prove* the engine.
- **`fnma_sf/`** — an optional connector for the real FNMA Single-Family Loan Performance file
  (loan-month panel → collapse to latest month → the unchanged 15 rules).
- **`backend/app/`** — FastAPI wiring for Modules A (ingestion), B (validation runner), C
  (exception workflow), D (AI), E (verified records), F (audit), H (read API). Consumes the
  shared libraries; never re-implements a rule.
- **`frontend/`** — a Vite/React/TS SPA with three role dashboards (Module G).

## Key decisions & trade-offs

**Mongo over Postgres.** Inbound loan files are messy and heterogeneous; a document store lets us
stage raw rows verbatim (`raw_records`) without up-front schema friction. We buy integrity where it
matters — the audit and verified-record trails — with an explicit **hash chain** rather than FK
constraints.

**One `HashChain`, two chains.** Both the audit log (Module F) and the verified-record chain
(Module E) are the same primitive: an atomic per-chain sequence number (a `counters` doc via
`$inc`), a **stable ISO-timestamp string** folded into the hash (raw `datetime`/`Decimal` are kept
out of the hashed body because BSON truncates/retypes them and would false-break the chain on real
Mongo), and a `verify()` that recomputes the chain end to end. Concurrent appends are serialized
with a per-chain lock. `verify()` proving `{ok: true}` is what earns the Traceability points without
a real blockchain (explicitly out of scope).

**Rules-first, ML-second.** Deterministic rule detection is auditable and matches the graded issue
list. The ML anomaly layer (Phase 2) is additive and low-severity, never load-bearing.

**LLM is suggestion-only, human-in-the-loop.** The AI never mutates data. It explains, suggests,
compares, classifies, and summarizes; every call and every accept/edit/reject decision is written
to `ai_recommendations` and the audit log with provider/model/prompt/timestamp. Applying a
suggestion is an explicit reviewer edit through the resolve endpoint.

**Mock AI fallback.** A single `AIProvider` interface has a deterministic `MockProvider` (default,
the test path, zero-key demo) and a `ClaudeProvider` (`claude-sonnet-5`, used only when a key is
set). If Claude errors at runtime, the service **falls back to Mock** so a flaky network never
breaks a demo.

**Synthetic tape is the graded oracle; real data is stretch.** Only the synthetic package has
ground truth, so it's the source we can prove correctness against. The FNMA connector adds
real-data credibility but has no ground truth — it validates behavior, not correctness.

**Surrogate key discipline crosses into the backend.** Validation keys off each loan's Mongo `_id`
(genuinely unique per row), never `loan_id` — because `duplicate_loan_id` deliberately collides
`loan_id`s. This is what lets the ground-truth oracle re-detect *all 15* rule types with no
carve-out. Rows with no `loan_id` at all are correctly *failed imports* (their findings live in the
dataset summary, not the exception queue).

**Normalization vs. validation boundary.** Ingestion is lenient: only a missing primary key fails a
row. A malformed-but-present value (e.g. an unparseable date) is preserved so the *rules* — not the
parser — flag it. This mirrors exactly what `loan_rules` is designed to catch and keeps the two
concerns cleanly separated.

**Grain-aware rules over forking the product.** A `profiles` dimension on `Rule` lets the same
engine validate panel data (Pass 1) and, after a latest-month collapse (Pass 2), reuse the
unchanged loan-grain rules (Pass 3). The graded loan-tape path is untouched.

## Data model (8 collections)

`users`, `datasets`, `raw_records`, `loans`, `exceptions`, `ai_recommendations`,
`verified_records`, `audit_log` (+ a `counters` helper for atomic chain sequence). The
`{rule_id, field, observed_value, expected, sibling_value?, message}` bundle is one shape shared by
the generator's ground truth, the exception record, and the AI's grounding.

## Lifecycle

`imported → validated → in_review → verified | rejected`, with every graded transition appended to
the audit chain (bulk validation emits one summary event; reviewer actions are per-event).

## Testing strategy

Offline unit tests run against `mongomock-motor`; a real-Mongo integration lane covers the cases
mongomock hides (hash-chain BSON round-trips, `Decimal128`, append concurrency). The engine is
verified by an end-to-end **superset-oracle** test: ingest the generated 3-file package, validate,
and assert every ground-truth exception on every imported loan is re-detected.
