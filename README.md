# Loan Data Verification Copilot

An AI-assisted loan-data verification platform: ingest messy loan files, validate them against
15 data-driven rules, triage the resulting exceptions with a human-in-the-loop AI assistant,
verify records, and expose everything through a tamper-evident audit trail and a read API.

Built for the Full-Stack Track. Modules A–H per the brief, plus two optional stretch pieces
(a real-data FNMA connector and a seeded synthetic-data generator with a machine-checkable
ground-truth oracle).

---

## Quick start (one command)

```bash
cp .env.example .env          # optional; sensible defaults ship in docker-compose
docker compose up --build
```

- **Web UI** → http://localhost:5173
- **API + interactive docs** → http://localhost:8000/docs

The API seeds users and a graded synthetic dataset on startup. With **no** `LVC_ANTHROPIC_API_KEY`
set, the AI assistant runs on a deterministic **MockProvider** — the whole app works offline.

### Test credentials (all three roles)

| Role | Username | Password | Sees |
|---|---|---|---|
| Data Operator | `operator` | `operator123` | Upload + validate, import history, quality summary |
| Reviewer | `reviewer` | `reviewer123` | Exception queue, AI panel, resolve/edit/approve, verify |
| Data Consumer | `consumer` | `consumer123` | Verified records, quality score, audit trail, export |

---

## Demo flow (≤5 min)

1. **Operator** logs in → uploads `loan_tape.csv` (+ optional `servicer_update.csv`,
   `document_manifest.csv`) → clicks **Upload + Validate** → sees imported/failed/exception counts
   and a quality score. (Generate a sample bundle with `make seed`; files land in `data/`.)
2. **Reviewer** logs in → filters the exception queue → opens a loan → asks the **AI** to explain /
   suggest / compare → **applies** a suggestion (or approves/rejects) → **verifies** the loan.
3. **Consumer** logs in → browses verified records → opens the **audit trail** (shows a
   *chain intact ✓* badge) → **exports** the verified dataset as CSV.

---

## Architecture (one screen)

```
 React SPA (Vite/TS)                FastAPI + Beanie/Motor              MongoDB
 ├ Operator dashboard   ─────►  A  Ingestion  (parse→normalize→loans)   users, datasets,
 ├ Reviewer queue + AI  ─────►  B  Validation (15 loan_rules → exceptions)  raw_records,
 └ Consumer + audit     ─────►  C  Exception workflow  (resolve/edit)      loans, exceptions,
                                D  AI assistant  (Mock | Claude, HITL)     ai_recommendations,
                                E  Verified records  (record_hash chain)   verified_records,
                                F  Audit trail  (hash-chained log)         audit_log, counters
                                H  Public read API + export
```

- **Pure, shared libraries** (`loan_rules/`, `data/`, `fnma_sf/`) hold the validation engine, the
  synthetic-data generator, and the real-data connector. They are import-pure (no DB/web) and are
  **consumed** by the backend, never forked — one source of truth for the 15 rules and the
  canonical column set.
- **Two hash chains** (audit + verified records) share one `HashChain` primitive: atomic sequence
  numbers, a stable ISO-timestamp in the hash (BSON-safe), and `verify()` that proves integrity
  end to end.

See `docs/architecture-note.md` for the design rationale and trade-offs.

---

## Local development (without Docker)

```bash
make install         # creates .venv, installs backend + test deps + the shared libs
make seed            # generate the synthetic package into data/ (loan_tape.csv, users.json, …)
# start a mongo (e.g. `docker compose up mongo`), then:
LVC_MONGODB_URI=mongodb://localhost:27017 .venv/bin/uvicorn backend.app.main:create_app --factory --reload
# frontend:
cd frontend && npm install && npm run dev      # proxies /api → :8000
```

### Tests

```bash
make test            # offline unit suite (mongomock) — backend + engine + connector
# integration lane (real Mongo) — hash-chain + Decimal128 + concurrency:
LVC_TEST_MONGODB_URI=mongodb://localhost:27017 .venv/bin/python -m pytest -m integration
make test-all        # unit + frontend typecheck/build
```

The validation engine is verified against a **machine-generated ground-truth oracle**: the
generator injects defects and the runner must re-detect every one (`backend/tests/test_validation_runner.py`).

---

## Configuration

| Env var | Default | Purpose |
|---|---|---|
| `LVC_MONGODB_URI` | `mongodb://localhost:27017` | Mongo connection |
| `LVC_MONGODB_DB` | `lvc` | Database name |
| `LVC_JWT_SECRET` | `dev-secret-change-me` | JWT signing secret |
| `LVC_ANTHROPIC_API_KEY` | *(unset)* | If set, the AI uses Claude (`claude-sonnet-5`); else MockProvider |
| `LVC_TEST_MONGODB_URI` | *(unset)* | Enables the real-Mongo integration test lane |

---

## Repository layout

```
loan_rules/     # 15-rule validation engine (pure, shared) — Module B core
data/           # seeded synthetic-package generator + ground-truth oracle
fnma_sf/        # optional real-data FNMA SF connector (parse→normalize→collapse→validate)
backend/app/    # FastAPI: config, db, models, auth, chain, ingestion, validation, ai,
                #          verification, audit, api/   (Modules A,C,D,E,F,H)
frontend/       # React + Vite + TS SPA — 3 role dashboards (Module G)
docs/           # specs, plans, architecture note, AI development log, sample outputs
docker-compose.yml, Makefile
```

## Sample output

`docs/samples/verified-loans.sample.csv` (verified dataset export) and
`docs/samples/audit-trail.sample.json` (hash-chained audit export with a verification result) —
regenerate with `make samples` (needs a local Mongo).
