# Manual Test Plan — Loan Data Verification Copilot

A role-by-role walkthrough to verify the system end to end by hand. For each check:
**what to do → what you should see → why**, with the equivalent API call (Swagger at
http://localhost:8000/docs) and a direct DB peek so you can confirm at every layer.

**Setup:** `docker compose up --build`, then open http://localhost:5173 (UI) and
http://localhost:8000/docs (API). Reset any time with `docker compose down -v && docker compose up --build`.

---

## 1. The mental model

**One sentence:** messy loan files come in → get normalized and validated against 15 rules → the
resulting exceptions are triaged by a reviewer (with AI help) → good records are *verified* →
everything is exposed through a read API and a tamper-evident audit trail.

**Lifecycle of a loan:** `imported → validated → in_review → verified | rejected`

**Who can do what (enforced by JWT role):**

| Role | Can |
|---|---|
| **operator** | upload datasets, trigger validation, view import history |
| **reviewer** | view queue, run AI, edit/approve/reject exceptions, verify loans |
| **consumer** | read verified records, audit trail, summary, export |

Read endpoints (`/loans`, `/exceptions`, `/verified-loans`, `/summary`, `/audit/:id`) are open to
any logged-in user. Write/workflow endpoints are role-gated.

**The 8 collections** (each step writes specific ones):
`users` · `datasets` · `raw_records` · `loans` · `exceptions` · `ai_recommendations` ·
`verified_records` · `audit_log` (+ `counters` for the hash chains).

**Test credentials:** `operator/operator123` · `reviewer/reviewer123` · `consumer/consumer123`.

---

## 2. Operator — ingestion & validation (Modules A + B)

Log in as `operator`.

- [ ] **① Upload the 3 files** (`sample_data/loan_tape.csv`, `servicer_update.csv`,
  `document_manifest.csv`) → **Upload + Validate**.
  - **Expect:** tiles show `Rows 3000 · Imported ~2990 · Failed ~10 · Exceptions ~650 · quality ~87%`;
    a row appears in *Import history*.
  - **Why:** every raw row is stored (`raw_records`); each is normalized into `loans` with lineage;
    rows with no `loan_id` become *failed imports*; then the 15 rules produce `exceptions`.
  - **Verify (2nd terminal):**
    ```bash
    docker compose exec mongo mongosh lvc --quiet --eval '
     print("raw_records:", db.raw_records.countDocuments());
     print("loans:", db.loans.countDocuments());
     print("exceptions:", db.exceptions.countDocuments());
     print("failed rows:", db.datasets.findOne({},{failures:1}).failures.length)'
    ```

- [ ] **② Failed-import rows are separated, not crashed.**
  `db.datasets.findOne({}, {failures:1})` → a list of `{row_number, reason}` (rows where `loan_id`
  was blank). **Why:** Module A must survive un-normalizable rows and surface *why*.

- [ ] **③ Lineage.** `db.loans.findOne({}, {loan_id:1, dataset_id:1, normalized_from_raw_id:1})` →
  links back to its dataset and its exact raw row. **Why:** provenance for every canonical record.

---

## 3. Reviewer — triage, AI, verify (Modules C + D + E)

Log in as `reviewer`.

- [ ] **④ Queue + filter + search.** Change the **severity** dropdown → grid re-queries; type a
  loan id in **search** → filters. **Why:** Module C reviewer UX.

- [ ] **⑤ Open a loan → AI panel.** Click a row, then **Explain / Suggest / Compare**.
  - **Expect:** a response in a *separate* AI box with `provider: mock`, a confidence, and (for
    suggest/compare) a concrete suggested value. It never changes the loan on its own.
  - **Determinism:** click **Explain** twice → identical text (MockProvider).
  - **Verify:** `db.ai_recommendations.find().sort({created_at:-1}).limit(1).pretty()` — persisted
    with provider/model/prompt.

- [ ] **⑥ AI decision.** Click **Accept** or **Reject** on the AI box. **Why:** the decision is
  recorded (`ai_recommendations.decision`) and audited — separate from the human's own action.

- [ ] **⑦ Resolve.** Try **Apply edit** (applies the suggested value to an *allowed* field),
  **Approve**, **Reject**, **Request fix**.
  - **Expect:** the exception status changes (`accepted`/`resolved`/`rejected`/`open`); an edit
    actually changes the loan field.
  - **Guardrail:** editing a *disallowed* field returns **422** — in Swagger,
    `POST /exceptions/{id}/resolve` with `{"action":"edit","field":"loan_id","new_value":"X"}`.

- [ ] **⑧ Verify a loan.** Click **✓ Verify loan**.
  - **Expect:** a `record_hash` is returned; the loan's `lifecycle_state` becomes `verified`.
  - **Re-verify the same loan → 409** (already verified).
  - **Why:** Module E assembles a canonical verified record and hashes it into a chain.

- [ ] **⑨ Per-loan history.** `GET /loans/{loan_id}/history` (Swagger) → an ordered list of every
  action taken on that loan. **Why:** Module C action history / traceability.

---

## 4. Consumer — read, audit, export (Modules E + F + H)

Log in as `consumer`.

- [ ] **⑩ Verified records + summary.** Grid lists verified loans with record hashes; tiles show
  totals + quality. **Why:** Module E/H read surface.

- [ ] **⑪ Audit trail + chain badge.** Click **View trail** on a record → ordered audit entries and
  a **"chain intact ✓"** badge. **Why:** Module F — hash-chained, append-only log.

- [ ] **⑫ Export.** Click **⬇ Export CSV** → downloads the verified dataset with the 21 canonical
  columns. **Why:** §13 sample output / Module H.

---

## 5. Prove the hard parts

- [ ] **A. Tamper-evidence.** The chain must *break* if history is edited:
  ```bash
  TOK=$(curl -s -XPOST localhost:8000/auth/login -d 'username=reviewer&password=reviewer123' \
        | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')
  curl -s localhost:8000/audit/verify -H "Authorization: Bearer $TOK"      # {"ok":true,...}
  docker compose exec mongo mongosh lvc --quiet --eval \
    'db.audit_log.updateOne({seq:2},{$set:{"payload.tampered":true}})'
  curl -s localhost:8000/audit/verify -H "Authorization: Bearer $TOK"      # {"ok":false,"broken_at":2}
  ```
  Reset afterward: `docker compose down -v && docker compose up --build`.

- [ ] **B. Field-availability gating (the FNMA fix).** Upload `data/fnma_loan_tape.csv` as a lone
  `loan_tape` → validate → `quality ~99.9%` and the response's `gated_rules` lists
  `required_fields:borrower_id` + `document_status_present`. **Why:** the engine validates what the
  source provides instead of flooding on structurally-absent fields.
  *(Generate the tape first if missing: `make fnma-demo`, needs `2025Q1.csv`.)*

- [ ] **C. Reproducible ground-truth oracle (the correctness proof).**
  ```bash
  .venv/bin/python -m pytest backend/tests/test_validation_runner.py -q
  ```
  Generates a package with known defects, ingests + validates through the real code, and asserts
  **every** ground-truth exception on every imported loan is re-detected — no carve-outs.

- [ ] **D. AI works with zero key.** No `LVC_ANTHROPIC_API_KEY` → all AI runs on the deterministic
  mock. Set a key in `.env` and rebuild to see `provider: claude`; a network failure falls back to
  `mock (claude-fallback)`.

---

## 6. Peek at anything directly

```bash
docker compose exec mongo mongosh lvc          # interactive shell
#   db.loans.findOne()          db.exceptions.find({severity:"high"}).limit(3)
#   db.verified_records.find({}, {loan_id:1, record_hash:1, seq:1})
#   db.audit_log.find({}, {seq:1, event_type:1, actor:1}).sort({seq:1})
docker compose logs -f api                      # request + startup logs
```

Swagger (http://localhost:8000/docs): click **Authorize**, paste a token from `POST /auth/login`,
and every endpoint is runnable there.

---

## Full automated suite (optional, needs Python 3.12 locally)

```bash
make install && make test      # 119 unit tests (offline, mongomock)
LVC_TEST_MONGODB_URI=mongodb://localhost:27017 .venv/bin/python -m pytest -m integration   # real-Mongo lane
```
