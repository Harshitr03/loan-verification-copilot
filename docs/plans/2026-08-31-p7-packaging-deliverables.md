# P7 — Packaging + Deliverables — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the whole system run with one command (`docker compose up` → web + api + mongo, seeded) and produce every §13 deliverable: README with test credentials, architecture note, AI development log, and a committed sample verified-output + audit export.

**Architecture:** `docker-compose.yml` orchestrates `mongo`, `api` (uvicorn on the backend image), `web` (built Vite app served by nginx or vite preview). A root `Makefile` wraps up/down/seed/test. Docs are assembled from the existing spec/TDD/review trail — the repo already contains the raw material (specs, per-task commits, the two review-driven bug fixes).

**Tech Stack:** Docker, docker-compose, nginx (static web) or `vite preview`, the P1–P6 apps, Makefile.

**Spec:** parent §13 (deliverables), §14 (repo layout), §17 (trade-offs → architecture note). Depends on **P1–P6 green**. Roadmap P7.

## Global Constraints

- **One-command run (spec §13):** `docker compose up` brings the app up and seeds data; the README states this verbatim.
- **Zero-key demo:** with no `ANTHROPIC_API_KEY`, the AI runs on `MockProvider` (P4) so the demo works offline; the README documents the optional key.
- **Test credentials for all 3 roles (spec §3, §13):** documented in the README, sourced from the seeded `data/users.json` (passwords are the generator's `operator123`/`reviewer123`/`consumer123`).
- **Sample output committed (spec §13):** a verified-loans export + an audit-trail export checked into `docs/samples/` (small, deterministic where possible).
- Reuse the existing `Makefile` (generator/connector targets) — extend, don't replace.

---

## File Structure

```
docker-compose.yml
.env.example
backend/Dockerfile
frontend/Dockerfile           # multi-stage build -> nginx static
frontend/nginx.conf
Makefile                      # extend: up, down, logs, seed-db, test-all
README.md
docs/
  architecture-note.md
  ai-development-log.md
  samples/
    verified-loans.sample.csv
    audit-trail.sample.json
backend/tests/test_compose_smoke.py   # optional: skipped unless COMPOSE_UP=1
```

---

### Task 1: Backend Dockerfile + compose (api + mongo)

**Files:** Create `backend/Dockerfile`, `docker-compose.yml`, `.env.example`.

**Interfaces:** `api` service builds from `backend/Dockerfile` (python:3.12-slim, `pip install -e ".[backend]"`, `uvicorn backend.app.main:create_app --factory --host 0.0.0.0 --port 8000`), depends on `mongo` (with a healthcheck), reads `LVC_MONGODB_URI=mongodb://mongo:27017`, `LVC_JWT_SECRET`, `LVC_ANTHROPIC_API_KEY?`. `mongo:7` service with a named volume.

- [ ] **Step 1: Write** `backend/Dockerfile`, `docker-compose.yml` (`mongo`, `api`), `.env.example`.
- [ ] **Step 2: Verify** — `docker compose up -d mongo api` then `curl localhost:8000/health` → `{"status":"ok"}`; `curl localhost:8000/docs` serves OpenAPI.
- [ ] **Step 3: Commit** `chore(deploy): backend Dockerfile + compose (api+mongo)`.

---

### Task 2: Makefile targets (lifespan init/seed already in P1)

**Files:** Modify `Makefile`. (The FastAPI `lifespan` that runs `init_db` + `seed_users` was moved into P1's `create_app`, finding #5 — so the app already seeds on boot; nothing to add here but the ergonomics.)

**Interfaces:** Makefile: `make up` (`docker compose up --build`), `make down`, `make logs`, `make seed-db` (runs the generator `make seed` to (re)produce `data/*.csv` + `users.json`, then restarts `api` so its lifespan re-seeds users), `make test-all` (`pytest -q` + `pytest -m integration` when `LVC_TEST_MONGODB_URI` is set + `cd frontend && npm test`).

- [ ] **Step 1: Write** the Makefile targets.
- [ ] **Step 2: Verify** — `make up` brings the stack up; api logs show the lifespan seeding N users; `POST /auth/login` (form) with `reviewer/reviewer123` returns a token.
- [ ] **Step 3: Commit** `chore(deploy): make up/down/logs/seed-db/test-all`.

---

### Task 3: Frontend Dockerfile + web service

**Files:** Create `frontend/Dockerfile`, `frontend/nginx.conf`; modify `docker-compose.yml` (add `web`).

**Interfaces:** Multi-stage: `node:20` builds the Vite app with `VITE_API_BASE=/api`; `nginx:alpine` serves it and reverse-proxies `/api` → `api:8000`. `web` service on port 5173/80.

- [ ] **Step 1: Write** the Dockerfile + nginx config + compose `web` service.
- [ ] **Step 2: Verify** — `docker compose up` → open the web port, log in as each role, walk the demo flow manually.
- [ ] **Step 3: Commit** `chore(deploy): frontend image + web service (nginx + /api proxy)`.

---

### Task 4: README + test credentials

**Files:** Create `README.md`.

**Interfaces:** Sections: overview, architecture diagram (ascii/mermaid), **quick start (`docker compose up`)**, env vars (`LVC_*`, optional `LVC_ANTHROPIC_API_KEY` → mock fallback), **test credentials table for all 3 roles**, running tests (`make test-all`), regenerating data (`make seed`), the FNMA connector note, project layout, and links to the specs + architecture note + AI dev log.

- [ ] **Step 1: Write** `README.md` (credentials sourced from `data/users.json`: `operator/operator123`, `reviewer/reviewer123`, `consumer/consumer123`).
- [ ] **Step 2: Verify** — a fresh clone following the README reaches a working login. - [ ] **Step 3: Commit** `docs: README with quick start + test credentials`.

---

### Task 5: Architecture note + AI development log

**Files:** Create `docs/architecture-note.md`, `docs/ai-development-log.md`.

**Interfaces:**
- `architecture-note.md` (1–2 pp) — distilled from spec §17 trade-offs: Mongo-over-Postgres, rules-first/ML-second, LLM-suggestion-only, mock-AI fallback, synthetic-oracle-vs-real-data, grain-aware profiles, hash-chain-over-blockchain; plus the module map and data flow.
- `ai-development-log.md` — tools used (Claude Code), 5–10 representative prompts (pull from this repo's spec/plan/execution history), the human-review process (per-task TDD checkpoints + the deep-review passes), AI-code % estimate, **≥2 rejected-AI examples** (e.g. the footprint-composition bug and the `-0.00` corrupt bug caught by the multi-seed oracle; plus any P4 rejected suggestions), and lessons learned.

- [ ] **Step 1: Write** both docs from the existing artifacts. - [ ] **Step 2: Commit** `docs: architecture note + AI development log`.

---

### Task 6: Sample verified output + audit export

**Files:** Create `docs/samples/verified-loans.sample.csv`, `docs/samples/audit-trail.sample.json`.

**Interfaces:** Generate by running the stack end-to-end on the seeded synthetic tape: upload → validate → resolve/verify a handful of loans → export. Commit the exports as the §13 sample output.

- [ ] **Step 1:** run the flow (script it), export via `/verified-loans/export` + `/audit/export`, save under `docs/samples/`. - [ ] **Step 2: Commit** `docs: sample verified output + audit trail export`.

---

### Task 7: Compose smoke test (optional, gated)

**Files:** Create `backend/tests/test_compose_smoke.py`.

**Interfaces:** a test `@pytest.mark.skipif(os.getenv("COMPOSE_UP") != "1")` that hits `http://localhost:8000/health`, logs in as each role, and verifies `/summary` — a CI hook for the packaged stack.

- [ ] Standard TDD (skipped by default). Commit `test(deploy): gated compose smoke`.

---

## Self-Review

**1. Spec coverage:** §13 working app (`docker compose up`) → T1–T3; README + credentials → T4; architecture note → T5; AI development log (tools/prompts/review/%/≥2 rejects/lessons) → T5; sample verified output + audit export → T6; demo video is user-recorded (out of code scope, README documents the §15 script). §14 repo layout → matches (compose, Dockerfiles, docs/).

**2. Placeholder scan:** each deliverable is a concrete file with defined content; credentials are the real seeded values. No TODO.

**3. Type/name consistency:** reuses `create_app` (P1, `--factory`), `seed_users` (P1), `/health` (P1), export endpoints (P5), `VITE_API_BASE`/`/api` proxy (P6). Env var names (`LVC_*`) match P1 `Settings` prefix.

## Notes for the executor
- The AI development log's rejected-AI examples already exist in this repo's history (the two multi-seed-caught bugs); cite them with commit refs.
- Keep sample exports small + regenerable; note the seed used so they can be reproduced.
- Demo video is the user's to record against the README's §15 script; the plan provides everything it needs to run.
