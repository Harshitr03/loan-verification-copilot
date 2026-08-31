# AI Development Log

This project was built with **Claude Code** (Anthropic) as a pair-programming agent, under
continuous human review. This log documents how AI was used, how its output was checked, and where
it was corrected or rejected.

## Tools

- **Claude Code** (agentic CLI) — spec authoring, TDD implementation, refactoring, review.
- Human developer — direction, design decisions, per-task review gates, all git commits.

## Process

Work was driven **spec-first, then plan-first, then test-first**:

1. Design specs authored and reviewed (`docs/specs/`).
2. Specs decomposed into bite-sized, TDD implementation plans (`docs/plans/`), each task = failing
   test → run (confirm red) → minimal implementation → run (confirm green) → commit.
3. Each task reviewed at a checkpoint before proceeding. Several rounds of deep design review were
   run against the plans *before* code, catching issues while they were cheap to fix.

AI wrote the large majority of the code and tests; the human owned every architectural decision,
reviewed each task, and made every commit. **Estimated AI-authored code: ~85–90%**, all
human-reviewed; 100% of design decisions and commits human-owned.

## Representative prompts

1. *"Design the synthetic data generator so injection and detection can never drift — one `Rule`
   object carries both `check` and `corrupt`, and the generator emits a ground-truth bundle for
   every implicated loan."*
2. *"Decompose full-stack completion into sequenced subsystem plans (foundation/auth/audit →
   ingestion+validation → queue+verified → AI → public API → frontend → packaging), each producing
   working, testable software."*
3. *"Wire the 15 `loan_rules` into a FastAPI validation runner that reproduces the generator's
   ground-truth superset — reuse the engine, never re-implement a rule."*
4. *"Add a hash-chained audit log with an integrity-verify endpoint; make it survive a real-Mongo
   round-trip."*
5. *"Implement the AI assistant with a deterministic MockProvider default and a key-gated
   ClaudeProvider, human-in-the-loop, every call and decision audited."*

## Human review caught real AI mistakes (rejected / corrected AI output)

These are cases where AI-generated code looked correct, passed a first-pass test, and was **rejected
or corrected** on review — evidence that the review gate did real work:

1. **Row-defect composition bug (rejected).** The generator's allocator let two field-colliding
   corruptions land on the same loan, which crashed or silently *healed* an earlier defect. A
   single lucky seed hid it; a **multi-seed** superset-oracle test exposed it. Fixed with
   footprint-aware allocation (rules that touch a shared field are never co-located).
2. **`-0.00` corruption (rejected).** `non_negative_amounts.corrupt` produced `-abs(0.00)` on a
   zero balance — not `< 0`, so the injected defect was undetectable and the oracle broke. Fixed to
   force a strictly-negative value; pinned with a regression test.
3. **Hash-chain timestamp bug (rejected in review).** The audit hash originally folded a raw
   `datetime`; BSON truncates to milliseconds, so `verify()` false-broke on real Mongo while
   passing under mongomock. Corrected to hash a stable ISO string. A real-Mongo integration lane was
   added because mongomock had been hiding this whole class of bug.
4. **Chain concurrency + nested-value drift (rejected in review).** Two more real-Mongo-only chain
   bugs — a non-atomic append that forks the chain under concurrency, and nested `datetime`/`Decimal`
   in a hashed field drifting through BSON. Both were proven failing against real Mongo, then fixed
   (per-chain lock; centralized deep-canonicalization of hashed values).
5. **Surrogate-key regression (corrected).** An early plan keyed validation off `loan_id` and hid
   the resulting ambiguity with an oracle carve-out. Rejected in review; changed to key off the
   Mongo `_id`, restoring a carve-out-free proof.
6. **Ingestion/validation boundary (corrected during implementation).** The first normalizer
   *rejected* rows with malformed dates as failed imports, so the `valid_dates` rule never got to
   flag them and the oracle missed loans. Corrected to a lenient boundary: only a missing primary
   key fails a row; malformed-but-present values are preserved for the rules.

## Lessons

- **Determinism + a ground-truth oracle is the highest-leverage test.** It caught composition and
  edge-value bugs that no single example test would have.
- **mongomock is convenient but hides real-store behavior** (timestamp precision, Decimal128,
  concurrency). A thin real-Mongo integration lane is worth it for anything integrity-critical.
- **Review before code pays off.** Multiple design-review rounds on the plans fixed structural
  issues (route ownership, hash-chain atomicity, 3-file ingestion) before a line was written.
- **Reuse discipline matters.** Keeping the rules/generator/connector as pure shared libraries and
  having the backend *consume* them kept one source of truth and prevented drift.
