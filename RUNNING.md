# Running the Loan Verification Copilot (for reviewers)

A one-command, fully-offline demo. **You only need Docker** — no Python, Node, database, or API key.

---

## 1. Prerequisites

- **Docker Desktop** (macOS/Windows) or **Docker Engine + Compose v2** (Linux), running.
  Check with:
  ```bash
  docker --version && docker compose version
  ```
- Free local ports **5173** (web) and **8000** (API). The database runs *inside* Docker and is
  not exposed, so it won't clash with anything on your machine.
- ~2 GB free disk for images. No internet needed after the first image pull.

---

## 2. Start it (one command)

From the project root:

```bash
docker compose up --build
```

The first run builds three containers (Mongo, API, web) and generates seed data — this takes a
few minutes. **It's ready when the API log prints Uvicorn running on `http://0.0.0.0:8000`.**

To run it in the background instead: `docker compose up --build -d` (then `docker compose logs -f`).

---

## 3. Open it

| What | URL |
|---|---|
| **Web app** | http://localhost:5173 |
| **API docs (Swagger)** | http://localhost:8000/docs |

### Login — three seeded roles

| Role | Username | Password |
|---|---|---|
| Data Operator | `operator` | `operator123` |
| Reviewer | `reviewer` | `reviewer123` |
| Data Consumer | `consumer` | `consumer123` |

---

## 4. Guided demo (~4 minutes — exercises every module)

A ready-to-upload sample dataset is in this repo at **`sample_data/`** (three CSVs).

**A. Data Operator** — *ingestion + validation (Modules A, B)*
1. Log in as `operator`.
2. Under **Upload & validate**, choose the three files from `sample_data/`:
   `loan_tape.csv` (required), `servicer_update.csv`, `document_manifest.csv`.
3. Click **Upload + Validate**. You'll see **rows / imported / failed / exceptions** and a
   **quality score**, plus the dataset in *Import history*.

**B. Reviewer** — *exception triage + AI + verification (Modules C, D, E)*
1. Log out, log in as `reviewer`.
2. The **exception queue** lists findings. Filter by severity/status or search a loan id.
3. Click a row to open the loan. In the **AI assistant** panel click **Explain / Suggest /
   Compare** — the AI response renders separately (deterministic mock; no key needed). Accept or
   reject it.
4. Use **Apply edit / Approve / Reject**, then **✓ Verify loan** — you'll get a record hash.

**C. Data Consumer** — *verified records + audit trail + export (Modules E, F, H)*
1. Log out, log in as `consumer`.
2. See the **verified records**, quality score, and totals.
3. Click **View trail** on a record — the audit trail shows a **"chain intact ✓"** badge
   (tamper-evident hash chain).
4. Click **⬇ Export CSV** to download the verified dataset.

You can also explore the full REST API at **http://localhost:8000/docs** (click *Authorize*,
log in with any of the accounts above, and try `GET /summary`, `GET /audit/verify`, etc.).

---

## 5. Stop / reset

```bash
docker compose down        # stop the app
docker compose down -v      # stop and wipe the database (fresh start next time)
```

---

## 6. Optional

- **Use real Claude instead of the mock AI:** create a `.env` file with
  `LVC_ANTHROPIC_API_KEY=sk-...` before `docker compose up`. Without a key the app runs the
  deterministic MockProvider so the demo works fully offline.
- **Run the test suite** (needs Python 3.12 locally, not required for the demo):
  ```bash
  make install && make test        # unit suite (offline)
  ```

---

## 7. Troubleshooting

| Symptom | Fix |
|---|---|
| `Cannot connect to the Docker daemon` | Start Docker Desktop and retry. |
| Port 5173 or 8000 already in use | Stop the other process, or edit the `ports:` in `docker-compose.yml`. |
| Web page loads but calls fail | Give the API a few more seconds on first boot (it seeds on startup); refresh. |
| Want a clean slate | `docker compose down -v` then `docker compose up --build`. |

Architecture and design rationale: **`docs/architecture-note.md`**.
AI-assisted development log: **`docs/ai-development-log.md`**.
