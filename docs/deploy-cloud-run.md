# Deploy — Frontend on AWS Amplify, Backend on Google Cloud Run

A free-tier split deploy: static React on **Amplify**, the FastAPI container on **Cloud Run**
(scales to zero), and **MongoDB Atlas M0** (free) for persistence.

```
 Browser ──> Amplify (static SPA) ──HTTPS──> Cloud Run (FastAPI) ──> MongoDB Atlas (M0)
             VITE_API_BASE ─────────────────┘
```

Why this shape: Cloud Run has no always-on server to pay for (it scales to zero), the image is
your existing `Dockerfile`, and Atlas holds the data so a cold-started container keeps its state.

---

## 0. One-time prerequisites

- A Google account with **billing enabled** (Cloud Run has an always-free allowance — 2M requests/mo;
  a demo stays well within it, but a billing account must exist).
- Install the CLI: <https://cloud.google.com/sdk/docs/install>, then:
  ```bash
  gcloud init                    # log in, pick/create a project
  gcloud auth login
  ```
- A MongoDB Atlas account: <https://www.mongodb.com/cloud/atlas/register>

---

## 1. MongoDB Atlas (free M0 cluster)

1. Create a **Shared / M0** cluster (free).
2. **Database Access** → add a database user (username + password). Save them.
3. **Network Access** → add IP `0.0.0.0/0` (allow from anywhere — demo-grade; Cloud Run has no
   fixed egress IP on the free path, so this is the simplest option).
4. **Connect → Drivers** → copy the connection string. It looks like:
   ```
   mongodb+srv://<user>:<pass>@cluster0.xxxx.mongodb.net/?retryWrites=true&w=majority
   ```
   Replace `<user>`/`<pass>` with the DB user from step 2. This is your `LVC_MONGODB_URI`.

## 2. Seed the database once (from your laptop)

The app can seed itself on boot, but doing ~4,000 inserts over the network during Cloud Run's
startup can exceed its startup timeout. Cleaner: seed Atlas **once**, here, then deploy with the
boot-seed off.

```bash
# from the repo root, with the backend deps installed (.venv)
LVC_MONGODB_URI="mongodb+srv://<user>:<pass>@cluster0.xxxx.mongodb.net" \
LVC_MONGODB_DB="lvc" \
.venv/bin/python -m backend.app.demo_seed
# -> seeds the 3 users + ingests the deterministic dataset + verifies 10 loans
```

Verify in Atlas (Collections tab) that `lvc.verified_records` has 10 docs and `lvc.users` has 3.

## 3. Enable the Google Cloud APIs

```bash
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com
```

## 4. Deploy the backend to Cloud Run

`--source .` hands the repo to Cloud Build, which builds the root `Dockerfile` and deploys it.
(The `.gcloudignore` keeps the upload small.)

```bash
gcloud run deploy lvc-api \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --max-instances 1 \
  --memory 512Mi \
  --set-env-vars "LVC_MONGODB_DB=lvc,LVC_JWT_SECRET=<pick-a-long-random-string>,LVC_DEMO_SEED=0,LVC_CORS_ORIGINS=*" \
  --set-env-vars "^@^LVC_MONGODB_URI=mongodb+srv://<user>:<pass>@cluster0.xxxx.mongodb.net"
```

Notes:
- `LVC_DEMO_SEED=0` — the DB is already seeded (step 2); this keeps startup fast.
- `--max-instances 1` — avoids two cold-start instances racing to seed, and caps cost.
- The `^@^` on the second flag changes the delimiter to `@` so the `,` inside the Mongo URI
  isn't parsed as a separator. (Alternatively store the URI in Secret Manager — see step 7.)
- Cloud Run auto-injects `PORT=8080`; the Dockerfile's `${PORT:-8000}` picks it up.

When it finishes it prints a **Service URL** like `https://lvc-api-xxxxx-uc.a.run.app`. Test it:

```bash
curl https://lvc-api-xxxxx-uc.a.run.app/health          # {"status":"ok"}
curl https://lvc-api-xxxxx-uc.a.run.app/summary \
  -H "Authorization: Bearer $(curl -s -X POST https://lvc-api-xxxxx-uc.a.run.app/auth/login \
     -d 'username=consumer&password=consumer123' | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')"
```

## 5. Deploy the frontend to Amplify

1. Amplify Console → **New app → Host web app** → connect your GitHub repo.
2. **App root / monorepo:** set the build to run in `frontend/`.
3. Build settings (`amplify.yml` or the console equivalent):
   ```yaml
   version: 1
   applications:
     - appRoot: frontend
       frontend:
         phases:
           preBuild:  { commands: [ "npm ci" ] }
           build:     { commands: [ "npm run build" ] }
         artifacts:
           baseDirectory: dist
           files: [ "**/*" ]
   ```
4. **Environment variables** → add:
   ```
   VITE_API_BASE = https://lvc-api-xxxxx-uc.a.run.app
   ```
   Backend **origin only** — no trailing slash, no `/api` (the routes live at the root:
   `/auth/login`, `/loans`, …). Vite inlines this at build time, so redeploy after changing it.
5. Deploy. Amplify gives you a URL like `https://main.dxxxx.amplifyapp.com`.

## 6. Lock down CORS (optional but recommended)

Once you know the Amplify URL, tighten CORS from `*` to just that origin and redeploy the backend:

```bash
gcloud run services update lvc-api --region us-central1 \
  --update-env-vars "LVC_CORS_ORIGINS=https://main.dxxxx.amplifyapp.com"
```

## 7. Better secret handling (optional)

Instead of putting the Mongo URI in `--set-env-vars`, store it in Secret Manager:

```bash
printf 'mongodb+srv://<user>:<pass>@cluster0.xxxx.mongodb.net' | \
  gcloud secrets create lvc-mongo-uri --data-file=-
gcloud run services update lvc-api --region us-central1 \
  --set-secrets "LVC_MONGODB_URI=lvc-mongo-uri:latest"
```

---

## Environment variables (backend)

| Var | Example | Notes |
|---|---|---|
| `LVC_MONGODB_URI` | `mongodb+srv://…` | Atlas connection string |
| `LVC_MONGODB_DB` | `lvc` | Database name |
| `LVC_JWT_SECRET` | long random string | JWT signing secret — set a real one in prod |
| `LVC_CORS_ORIGINS` | `*` or `https://…amplifyapp.com` | Comma-separated allow-list |
| `LVC_DEMO_SEED` | `0` on Cloud Run | `1` locally to auto-seed on boot |
| `LVC_ANTHROPIC_API_KEY` | *(unset)* | Set to use real Claude; else the offline mock |

## Gotchas

- **Cold starts:** Cloud Run scales to zero; the first request after idle takes a few seconds.
  Hit `/health` once to warm it right before a live demo.
- **Re-seeding:** to reset the demo data, drop the `lvc` database in Atlas and re-run step 2.
- **Free-tier CPU:** Cloud Run only allocates CPU during requests, so don't rely on background
  work between requests — that's exactly why we seed out-of-band (step 2) instead of on boot.
