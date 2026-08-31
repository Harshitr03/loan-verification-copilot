# P1 — Backend Foundation + Auth + Audit Chain — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the FastAPI + MongoDB (Motor/Beanie) backend spine — app factory, config, all 8 Beanie document models, user seeding, JWT role auth, and the hash-chained audit log with an integrity-verify endpoint — that every later plan (P2–P7) builds on.

**Architecture:** A `backend/app` package: `config` (pydantic-settings), `db` (Beanie init over Motor), `models` (the 8 collections from spec §5), `auth` (JWT with a role claim seeded from `users.json`), `audit` (append-only hash chain). Import-pure `loan_rules`/`data` are consumed later, never modified. Tests run offline against `mongomock-motor`; docker-compose (P7) supplies a real Mongo for e2e.

**Tech Stack:** Python 3.12, FastAPI, Uvicorn, Motor, Beanie, pydantic v2 + pydantic-settings, python-jose[cryptography] (JWT), passlib[bcrypt] / bcrypt, pytest + pytest-asyncio + httpx (async test client), mongomock-motor (offline test DB).

**Spec:** `docs/specs/2026-08-27-loan-verification-copilot-design.md` §2 (stack), §3 (roles), §5 (data model), §9 (audit hash chain), §11 (endpoints). Roadmap: `docs/plans/2026-08-31-full-stack-completion-roadmap.md` (P1).

## Global Constraints

- **Python 3.12**; backend lives under `backend/app/`, installed via the existing root `pyproject.toml` (add a `[project.optional-dependencies] backend = [...]` group; do **not** disturb the `loan_rules`/`fnma_sf` packages list).
- **Reuse, never fork:** the backend imports `loan_rules` and `data._serialize`; it must not redefine a rule or the canonical column list.
- **Async everywhere:** all DB access is `await`ed; every test is `@pytest.mark.asyncio`. `pytest.ini_options` gets `asyncio_mode = "auto"`.
- **Hash chains (spec §9), one shared implementation:** a single `chain.HashChain(model)` powers **both** the audit chain and the verified-record chain. `entry_hash = sha256(prev_hash + canonical_json(hashed_body))`; `canonical_json` = `json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)`. First entry uses `prev_hash = ""`.
  - **Stable timestamp:** the hashed body carries an explicit **ISO-8601 string** (`ts_iso`), not a `datetime` — BSON truncates datetimes to milliseconds, so hashing the raw datetime makes `verify` fail against real Mongo while passing under mongomock (in-memory µs). Store and hash the exact string; keep any queryable `datetime` field **out** of the hashed body.
  - **Atomic seq:** the next `seq` is reserved atomically via a `Counter` doc (`find_one_and_update({_id:name}, {$inc:{value:1}}, upsert=True, return new)`), never read-max-then-insert (that TOCTOU-forks the chain under concurrency/async interleaving).
- **Integration lane:** unit tests use `mongomock-motor` (fast, offline); a **real-Mongo lane** (`@pytest.mark.integration`, skipped unless `LVC_TEST_MONGODB_URI` is set → the docker `mongo`) covers the hash chain + `Decimal128` round-trips, so the graded integrity is verified against the store we actually ship, not just mongomock.
- **JWT (spec §2, demo-grade):** HS256, `{sub: username, role, exp}`; secret from settings; roles are exactly `data_operator | reviewer | data_consumer` (spec §3, matching `data/generate.py` USERS).
- **Money = `Decimal`, dates = `date`/`datetime`** in models; Mongo stores Decimal via `bson.Decimal128` (Beanie handles `decimal.Decimal` fields).
- **Test DB isolation:** each test binds Beanie to a fresh `mongomock-motor` client (fixture), so `pytest -q` stays offline like the existing suite.

---

## File Structure

```
pyproject.toml                         # add [project.optional-dependencies] backend
backend/
  app/
    __init__.py
    config.py                          # Settings (env)
    canonical.py                       # canonical_json helper (shared by audit + verification)
    chain.py                           # HashChain(model): atomic seq + stable-ts append/verify
    db.py                              # init_db(client) binds Beanie models + indexes
    lifespan.py                        # startup: init_db(real client) + seed_users
    models/
      __init__.py                      # exports all documents + ALL_DOCUMENTS
      user.py  dataset.py  raw_record.py  loan.py
      exception.py  ai_recommendation.py  verified_record.py  audit_entry.py
      counter.py                       # {_id:name, value:int} for atomic seq
    auth.py                            # password hash, JWT (OAuth2 form login), get_current_user, require_role
    audit/__init__.py                  # thin wrapper over HashChain(AuditEntry): append(), verify_chain()
    api/
      __init__.py
      auth_router.py                   # POST /auth/login
      audit_router.py                  # GET /audit/verify
    main.py                            # create_app()
    seed.py                            # seed_users() from data/users.json
  tests/
    __init__.py
    conftest.py                        # event loop, mongomock Beanie init, app client, user fixtures
    test_health.py  test_models.py  test_seed_auth.py  test_audit_chain.py
```

---

### Task 1: App factory + config + health

**Files:**
- Create: `backend/app/__init__.py`, `backend/app/config.py`, `backend/app/main.py`, `backend/tests/__init__.py`, `backend/tests/conftest.py`, `backend/tests/test_health.py`
- Modify: `pyproject.toml`

**Interfaces:**
- Produces: `Settings` (`mongodb_uri: str`, `mongodb_db: str = "lvc"`, `jwt_secret: str`, `jwt_ttl_min: int = 480`, `anthropic_api_key: str | None = None`) via `get_settings()`; `create_app() -> FastAPI` mounting routers lazily; `GET /health -> {"status": "ok"}`.

- [ ] **Step 1: Add backend deps to `pyproject.toml`**

```toml
# append under [project.optional-dependencies]
backend = [
  "fastapi>=0.110", "uvicorn[standard]>=0.29", "motor>=3.4", "beanie>=1.26",
  "pydantic>=2.6", "pydantic-settings>=2.2", "python-jose[cryptography]>=3.3",
  "passlib[bcrypt]>=1.7", "pandas>=2.2", "python-multipart>=0.0.9",
]
test = [
  "pytest>=8", "pytest-asyncio>=0.23", "httpx>=0.27", "mongomock-motor>=0.0.29",
]
```

Add to `[tool.pytest.ini_options]`: `asyncio_mode = "auto"`.

- [ ] **Step 2: Write the failing test**

```python
# backend/tests/test_health.py
import pytest
from httpx import AsyncClient, ASGITransport
from backend.app.main import create_app


@pytest.mark.asyncio
async def test_health_ok():
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.get("/health")
    assert r.status_code == 200 and r.json() == {"status": "ok"}
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv/bin/python -m pip install -e ".[backend,test]" && .venv/bin/python -m pytest backend/tests/test_health.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend'` (add empty `backend/__init__.py` too).

- [ ] **Step 4: Write minimal implementation**

```python
# backend/app/config.py
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LVC_", env_file=".env", extra="ignore")
    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_db: str = "lvc"
    jwt_secret: str = "dev-secret-change-me"
    jwt_ttl_min: int = 480
    anthropic_api_key: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

```python
# backend/app/lifespan.py
from contextlib import asynccontextmanager
from motor.motor_asyncio import AsyncIOMotorClient
from backend.app.config import get_settings
from backend.app.db import init_db
from backend.app.seed import seed_users


@asynccontextmanager
async def lifespan(app):
    s = get_settings()
    client = AsyncIOMotorClient(s.mongodb_uri)
    await init_db(client, s.mongodb_db)     # bind Beanie to the REAL mongo on boot
    try:
        await seed_users()                  # idempotent; no-op if users.json absent
    except FileNotFoundError:
        pass
    yield
```

```python
# backend/app/main.py
from fastapi import FastAPI
from backend.app.lifespan import lifespan


def create_app() -> FastAPI:
    app = FastAPI(title="Loan Verification Copilot API", lifespan=lifespan)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    from backend.app.api.auth_router import router as auth_router
    from backend.app.api.audit_router import router as audit_router
    app.include_router(auth_router)
    app.include_router(audit_router)
    return app
```

Note: create the router modules as empty `APIRouter()` stubs now so imports resolve; Tasks 4 & 7 fill them. `backend/__init__.py` and `backend/app/__init__.py` are empty. **The `lifespan` init/seed (moved here from P7, finding #5) makes the app runnable end-to-end from P1 on.** Tests are unaffected: httpx's `ASGITransport` does **not** fire lifespan events, and `conftest` binds Beanie to mongomock directly — so `create_app()` under test never touches real Mongo. `lifespan.py` imports `seed_users` (Task 3) and `init_db` (Task 2), so create those before wiring lifespan, or stub-import lazily.

- [ ] **Step 5: Run test to verify it passes** — Run: `.venv/bin/python -m pytest backend/tests/test_health.py -v` — Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml backend/__init__.py backend/app/ backend/tests/
git commit -m "feat(backend): app factory + settings + health"
```

---

### Task 2: Beanie models for all 8 collections + db init

**Files:**
- Create: `backend/app/models/*.py`, `backend/app/models/__init__.py`, `backend/app/db.py`, `backend/tests/conftest.py`, `backend/tests/test_models.py`

**Interfaces:**
- Produces: Beanie `Document`s `User, Dataset, RawRecord, Loan, Exception, AIRecommendation, VerifiedRecord, AuditEntry` (fields per spec §5) and `ALL_DOCUMENTS`; `init_db(client, db_name) -> None` calling `beanie.init_beanie`. `conftest.py` fixture `db` binds Beanie to a `mongomock_motor.AsyncMongoMockClient` and yields; `client` fixture yields an `AsyncClient` over `create_app()`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_models.py
import pytest
from decimal import Decimal
from backend.app.models import Loan, Exception as Exc, AuditEntry


@pytest.mark.asyncio
async def test_can_insert_and_query_loan(db):
    await Loan(loan_id="LN1", dataset_id="D1", original_principal=Decimal("100.00"),
              validation_status="pending", lifecycle_state="imported").insert()
    got = await Loan.find_one(Loan.loan_id == "LN1")
    assert got is not None and got.original_principal == Decimal("100.00")


@pytest.mark.asyncio
async def test_exception_bundle_shape(db):
    e = Exc(loan_id="LN1", dataset_id="D1", rule_id="interest_rate_range", type="ROW",
            severity="medium", source="rule", field="interest_rate",
            observed_value="99", expected="2-36", message="out of band", status="open")
    await e.insert()
    assert (await Exc.find_one(Exc.rule_id == "interest_rate_range")).field == "interest_rate"
```

```python
# backend/tests/conftest.py
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from mongomock_motor import AsyncMongoMockClient
from backend.app.db import init_db
from backend.app.main import create_app


@pytest_asyncio.fixture
async def db():
    client = AsyncMongoMockClient()
    await init_db(client, "lvc_test")
    yield client


@pytest_asyncio.fixture
async def client(db):
    async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://t") as c:
        yield c
```

- [ ] **Step 2: Run test to verify it fails** — Run: `.venv/bin/python -m pytest backend/tests/test_models.py -v` — Expected: FAIL — `ModuleNotFoundError: backend.app.models`.

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/models/loan.py
from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from beanie import Document
import pymongo


class Loan(Document):
    loan_id: str
    dataset_id: str
    borrower_id: Optional[str] = None
    loan_type: Optional[str] = None
    origination_date: Optional[date] = None
    maturity_date: Optional[date] = None
    original_principal: Optional[Decimal] = None
    current_balance: Optional[Decimal] = None
    interest_rate: Optional[Decimal] = None
    term_months: Optional[int] = None
    borrower_state: Optional[str] = None
    loan_purpose: Optional[str] = None
    credit_grade: Optional[str] = None
    employment_length: Optional[str] = None
    income_band: Optional[str] = None
    payment_status: Optional[str] = None
    days_past_due: Optional[int] = None
    servicer_name: Optional[str] = None
    last_payment_date: Optional[date] = None
    last_updated_at: Optional[datetime] = None
    document_status: Optional[str] = None
    source_system: Optional[str] = None
    normalized_from_raw_id: Optional[str] = None
    validation_status: str = "pending"        # pending|validated
    lifecycle_state: str = "imported"          # imported|validated|in_review|verified|rejected

    class Settings:
        name = "loans"
        indexes = [[("loan_id", pymongo.ASCENDING)]]
```

Create the remaining documents analogously, fields **verbatim from spec §5**:
- `user.py User`: `username, password_hash, role, display_name` (`Settings.name="users"`, unique index on `username`).
- `dataset.py Dataset`: `filename, file_type, source_system, uploaded_by, uploaded_at, row_count, imported_count, failed_count, status, column_mapping: dict, quality_score: float|None, failures: list[dict] = []` (`name="datasets"`). (`failures` holds `{row_number, reason}` for failed import rows — P2.)
- `raw_record.py RawRecord`: `dataset_id, row_number, raw: dict, source_file, file_type: str = "loan_tape"` (`name="raw_records"`). (`file_type ∈ {loan_tape, servicer_update, document_manifest}` — P2's 3-file ingestion.)
- `exception.py Exception`: `loan_id, loan_ref: Optional[str], dataset_id, rule_id, type, severity, source, field, observed_value, expected, sibling_value: Optional, message, status="open", ai_recommendation_id: Optional, resolution: Optional[dict]` (`name="exceptions"`, indexes on `status,severity,type`). `loan_ref` = the exact `Loan._id` (distinguishes the `duplicate_loan_id` pair, which shares `loan_id`). Import as `Exception` — alias to avoid shadowing the builtin.
- `ai_recommendation.py AIRecommendation`: `exception_id, loan_id, kind, provider, model, prompt, response, suggested_value: Optional, confidence: float, created_at, decision="pending", decided_by: Optional, decided_at: Optional` (`name="ai_recommendations"`).
- `verified_record.py VerifiedRecord`: `seq: int, loan_id, canonical_data: dict, source_file_ref, validation_result: dict, reviewer_decision: Optional[dict], ai_recommendation_ref: Optional, verified_at: datetime, ts_iso: str, verified_by, record_hash, prev_record_hash: Optional` (`name="verified_records"`, indexes on `loan_id` and `seq`). `seq` gives the chain a **defined order** (finding 1c); `ts_iso` is the hashed timestamp string, `verified_at` the queryable datetime (unhashed).
- `audit_entry.py AuditEntry`: `seq: int, event_type, entity_type, entity_id, actor, payload: dict, prev_hash, entry_hash, ts_iso: str, timestamp: datetime` (`name="audit_log"`, index on `seq`). `ts_iso` is hashed; `timestamp` is the queryable datetime (unhashed).
- `counter.py Counter`: `id: str` (the chain name, used as `_id`), `value: int = 0` (`name="counters"`). Backs atomic `seq` reservation.

```python
# backend/app/models/__init__.py
from backend.app.models.user import User
from backend.app.models.dataset import Dataset
from backend.app.models.raw_record import RawRecord
from backend.app.models.loan import Loan
from backend.app.models.exception import Exception
from backend.app.models.ai_recommendation import AIRecommendation
from backend.app.models.verified_record import VerifiedRecord
from backend.app.models.audit_entry import AuditEntry
from backend.app.models.counter import Counter

ALL_DOCUMENTS = [User, Dataset, RawRecord, Loan, Exception, AIRecommendation,
                 VerifiedRecord, AuditEntry, Counter]
__all__ = [d.__name__ for d in ALL_DOCUMENTS] + ["ALL_DOCUMENTS"]
```

```python
# backend/app/db.py
from beanie import init_beanie
from backend.app.models import ALL_DOCUMENTS


async def init_db(client, db_name: str) -> None:
    await init_beanie(database=client[db_name], document_models=ALL_DOCUMENTS)
```

- [ ] **Step 4: Run test to verify it passes** — Run: `.venv/bin/python -m pytest backend/tests/test_models.py -v` — Expected: PASS (2).

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/ backend/app/db.py backend/tests/conftest.py backend/tests/test_models.py
git commit -m "feat(backend): Beanie models for the 8 collections + db init"
```

---

### Task 3: User seeding from `data/users.json`

**Files:** Create `backend/app/seed.py`; Test `backend/tests/test_seed_auth.py` (seed part).

**Interfaces:** Produces `seed_users(path="data/users.json") -> int` — idempotent upsert into `users` (skip if username exists); returns count seeded. Reads the generator's `users.json` (`[{username, role, display_name, password_hash}]`).

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_seed_auth.py
import json
import pytest
from backend.app.models import User
from backend.app.seed import seed_users


@pytest.mark.asyncio
async def test_seed_is_idempotent(tmp_path, db):
    p = tmp_path / "users.json"
    p.write_text(json.dumps([{"username": "op", "role": "data_operator",
                              "display_name": "Op", "password_hash": "x"}]))
    assert await seed_users(str(p)) == 1
    assert await seed_users(str(p)) == 0            # already present
    assert await User.find_one(User.username == "op") is not None
```

- [ ] **Step 2: Run to verify fail** — `ModuleNotFoundError: backend.app.seed`.

- [ ] **Step 3: Implement**

```python
# backend/app/seed.py
import json
from backend.app.models import User


async def seed_users(path: str = "data/users.json") -> int:
    with open(path) as f:
        users = json.load(f)
    n = 0
    for u in users:
        if await User.find_one(User.username == u["username"]) is None:
            await User(username=u["username"], role=u["role"],
                       display_name=u["display_name"], password_hash=u["password_hash"]).insert()
            n += 1
    return n
```

- [ ] **Step 4: Run to verify pass.** - [ ] **Step 5: Commit** `feat(backend): idempotent user seeding from users.json`.

---

### Task 4: JWT auth — login + role dependencies

**Files:** Create `backend/app/auth.py`, `backend/app/api/auth_router.py`; Test extends `backend/tests/test_seed_auth.py`.

**Interfaces:** Produces `hash_password(pw)`, `verify_password(pw, h)`, `make_token(username, role)`, `decode_token(tok) -> dict`; FastAPI deps `get_current_user() -> User`, `require_role(*roles)`; `POST /auth/login` accepting **`OAuth2PasswordRequestForm`** (form-encoded `username`/`password`) → `{access_token, token_type, role}`. Form (not JSON) so FastAPI's Swagger **Authorize** button works out of the box (finding #7); the SPA (P6) posts form-encoded to match.

- [ ] **Step 1: Write the failing test**

```python
# add to backend/tests/test_seed_auth.py
import bcrypt
@pytest.mark.asyncio
async def test_login_returns_role_token(client, db):
    pw_hash = bcrypt.hashpw(b"secret", bcrypt.gensalt()).decode()
    await User(username="rev", role="reviewer", display_name="Rev", password_hash=pw_hash).insert()
    r = await client.post("/auth/login", data={"username": "rev", "password": "secret"})
    assert r.status_code == 200
    body = r.json()
    assert body["role"] == "reviewer" and body["token_type"] == "bearer" and body["access_token"]


@pytest.mark.asyncio
async def test_login_rejects_bad_password(client, db):
    import bcrypt
    await User(username="rev2", role="reviewer", display_name="R",
               password_hash=bcrypt.hashpw(b"a", bcrypt.gensalt()).decode()).insert()
    r = await client.post("/auth/login", data={"username": "rev2", "password": "wrong"})
    assert r.status_code == 401
```

- [ ] **Step 2: Run to verify fail** (404 — route absent).

- [ ] **Step 3: Implement**

```python
# backend/app/auth.py
from datetime import datetime, timedelta, timezone
import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from backend.app.config import get_settings
from backend.app.models import User

oauth2 = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


def verify_password(pw: str, h: str) -> bool:
    return bcrypt.checkpw(pw.encode(), h.encode())


def make_token(username: str, role: str) -> str:
    s = get_settings()
    exp = datetime.now(timezone.utc) + timedelta(minutes=s.jwt_ttl_min)
    return jwt.encode({"sub": username, "role": role, "exp": exp}, s.jwt_secret, algorithm="HS256")


def decode_token(tok: str) -> dict:
    return jwt.decode(tok, get_settings().jwt_secret, algorithms=["HS256"])


async def get_current_user(token: str = Depends(oauth2)) -> User:
    cred_exc = HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials")
    if not token:
        raise cred_exc
    try:
        payload = decode_token(token)
    except JWTError:
        raise cred_exc
    user = await User.find_one(User.username == payload.get("sub"))
    if user is None:
        raise cred_exc
    return user


def require_role(*roles):
    async def dep(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "insufficient role")
        return user
    return dep
```

```python
# backend/app/api/auth_router.py
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from backend.app.models import User
from backend.app.auth import verify_password, make_token

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login")
async def login(form: OAuth2PasswordRequestForm = Depends()):
    user = await User.find_one(User.username == form.username)
    if user is None or not verify_password(form.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "bad credentials")
    return {"access_token": make_token(user.username, user.role),
            "token_type": "bearer", "role": user.role}
```

(`OAuth2PasswordRequestForm` reads form-encoded `username`/`password`; needs `python-multipart`, already in the `backend` deps.)

- [ ] **Step 4: Run to verify pass.** - [ ] **Step 5: Commit** `feat(backend): JWT login + role dependencies`.

---

### Task 5: `chain.HashChain` — atomic, stable-timestamp hash chain (shared by both chains)

**Files:** Create `backend/app/canonical.py`, `backend/app/chain.py`; Test `backend/tests/test_chain.py`.

**Interfaces:** Produces `canonical_json(obj) -> str`; class `HashChain(model, name, *, prev_field="prev_hash", hash_field="entry_hash", ts_field="timestamp")` with:
- `async next_seq() -> int` — **atomic** reservation via `Counter.find_one_and_update({_id:name}, {$inc:{value:1}}, upsert=True, return_document=AFTER)` (no read-max-then-insert → no forked chains, finding 1b).
- `async append(**domain) -> model` — reserves seq, reads the tail's `hash_field` as `prev_hash`, builds `hashed_body = {"seq":seq, "ts_iso":now_iso, **domain}`, `entry_hash = sha256(prev_hash + canonical_json(hashed_body))`, persists `model(seq=seq, ts_iso=now_iso, **{ts_field: now_dt, prev_field: prev_hash, hash_field: entry_hash}, **domain)`, returns it. **The datetime is hashed only as the `ts_iso` string** (finding 1a); the `ts_field` datetime is stored unhashed for querying.
- `async append_many(rows: list[dict]) -> list[model]` — reserves a contiguous seq block, links locally, bulk-inserts (spec-literal per-item chaining; **not** used for bulk validation — P2 uses one summary event per the RC1 decision).
- `async verify() -> {"ok": bool, "broken_at": int|None}` — recompute in `seq` order; `domain` reconstructed from `model_dump()` minus the chain-metadata keys `{id, revision_id, seq, ts_iso, ts_field, prev_field, hash_field}`.

**Domain fields must be BSON-stable** (strings/ints/nested JSON, no raw `datetime`/`Decimal`) so `verify` after a real-Mongo round-trip hashes identically — the two lossy types (ms-truncated datetime, Decimal128) are the ones we keep out of the hashed body. Audit `payload`s are plain JSON dicts; the verified record's `canonical_data` is pre-serialized to strings (P3).

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_chain.py
import pytest
from backend.app.chain import HashChain
from backend.app.models import AuditEntry


@pytest.mark.asyncio
async def test_append_links_and_seq_is_atomic(db):
    ch = HashChain(AuditEntry, "audit")
    a = await ch.append(event_type="e1", entity_type="loan", entity_id="LN1", actor="op", payload={"v": 1})
    b = await ch.append(event_type="e2", entity_type="loan", entity_id="LN1", actor="op", payload={"v": 2})
    assert (a.seq, b.seq) == (1, 2)
    assert a.prev_hash == "" and b.prev_hash == a.entry_hash and b.entry_hash != a.entry_hash


@pytest.mark.asyncio
async def test_verify_detects_tampering(db):
    ch = HashChain(AuditEntry, "audit")
    await ch.append(event_type="e1", entity_type="loan", entity_id="LN1", actor="op", payload={"v": 1})
    await ch.append(event_type="e2", entity_type="loan", entity_id="LN1", actor="op", payload={"v": 2})
    assert (await ch.verify())["ok"] is True
    tail = await AuditEntry.find_one(AuditEntry.seq == 2)
    tail.payload = {"v": 999}; await tail.save()          # tamper
    res = await ch.verify()
    assert res["ok"] is False and res["broken_at"] == 2


@pytest.mark.asyncio
async def test_ts_iso_is_hashed_not_datetime(db):
    # regression for finding 1a: the hash must not depend on the ms-lossy datetime
    ch = HashChain(AuditEntry, "audit")
    e = await ch.append(event_type="e", entity_type="loan", entity_id="L", actor="op", payload={})
    e.timestamp = e.timestamp.replace(microsecond=0)      # simulate BSON ms truncation drift
    await e.save()
    assert (await ch.verify())["ok"] is True               # still valid: timestamp isn't hashed
```

- [ ] **Step 2: Run to verify fail** — `ModuleNotFoundError: backend.app.chain`.

- [ ] **Step 3: Implement**

```python
# backend/app/canonical.py
import json


def canonical_json(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)
```

```python
# backend/app/chain.py
import hashlib
from datetime import datetime, timezone
from backend.app.canonical import canonical_json
from backend.app.models import Counter


class HashChain:
    def __init__(self, model, name, *, prev_field="prev_hash",
                 hash_field="entry_hash", ts_field="timestamp"):
        self.model, self.name = model, name
        self.prev_field, self.hash_field, self.ts_field = prev_field, hash_field, ts_field

    async def next_seq(self) -> int:
        doc = await Counter.get_motor_collection().find_one_and_update(
            {"_id": self.name}, {"$inc": {"value": 1}}, upsert=True, return_document=True)
        return doc["value"]

    async def _tail(self):
        t = await self.model.find().sort(-self.model.seq).limit(1).to_list()
        return t[0] if t else None

    def _hash(self, prev_hash, seq, ts_iso, domain):
        body = {"seq": seq, "ts_iso": ts_iso, **domain}
        return hashlib.sha256((prev_hash + canonical_json(body)).encode()).hexdigest()

    async def append(self, **domain):
        seq = await self.next_seq()
        tail = await self._tail()
        prev_hash = getattr(tail, self.hash_field) if tail else ""
        now = datetime.now(timezone.utc)
        ts_iso = now.isoformat()
        h = self._hash(prev_hash, seq, ts_iso, domain)
        doc = self.model(seq=seq, ts_iso=ts_iso,
                         **{self.ts_field: now, self.prev_field: prev_hash, self.hash_field: h},
                         **domain)
        await doc.insert()
        return doc

    async def verify(self) -> dict:
        meta = {"id", "revision_id", "seq", "ts_iso", self.ts_field, self.prev_field, self.hash_field}
        prev_hash = ""
        async for e in self.model.find().sort(+self.model.seq):
            d = {k: v for k, v in e.model_dump().items() if k not in meta}
            if getattr(e, self.prev_field) != prev_hash or \
               getattr(e, self.hash_field) != self._hash(prev_hash, e.seq, e.ts_iso, d):
                return {"ok": False, "broken_at": e.seq}
            prev_hash = getattr(e, self.hash_field)
        return {"ok": True, "broken_at": None}
```

Note: `find_one_and_update` with `return_document=True` (pymongo `ReturnDocument.AFTER`) returns the incremented doc — under `mongomock-motor` and real Mongo alike this is atomic. `append_many` (reserve a seq block via a single `$inc: {value: len(rows)}`, then link locally) is a short addition; write it only if a later plan needs spec-literal per-item chaining.

**Two real-Mongo-only correctness fixes applied during execution (mongomock hid both, like the 1a bug — regression tests live in the integration lane, Task 7):**
- **F1 — concurrency fork:** the reserve-seq → read-tail → insert body is wrapped in a per-chain-name `asyncio.Lock` (`_lock_for(name)`). Without it, two overlapping appends fork the linkage (a seq-N entry pointing at seq-N+1's hash) and `verify()` false-breaks. Proven: `test_concurrent_appends_do_not_fork_the_chain` (25 concurrent appends) fails on real Mongo pre-fix, passes post-fix.
- **F2 — nested datetime/Decimal in a hashed field:** `append` deep-canonicalizes the whole `domain` via `_stable()` (datetime→isoformat, Decimal/Decimal128→str, recursive) **before both hashing and storing**, so the stored value equals the hashed value and both survive a BSON round-trip. This centralizes the "hashed values must be BSON-stable" invariant in the primitive — callers (audit payloads, verified `canonical_data`/`validation_result`/`reviewer_decision`) can't forget it. Proven: `test_nested_decimal_and_datetime_in_payload_survive`.
- Minor: `lifespan` now `client.close()`s the Motor client on shutdown.

- [ ] **Step 4: Run to verify pass** — `.venv/bin/python -m pytest backend/tests/test_chain.py -v`.
- [ ] **Step 5: Commit** `feat(backend): shared HashChain (atomic seq, stable-ts, verify)`.

---

### Task 6: Audit wrapper + `/audit/verify` endpoint

**Files:** Create `backend/app/audit/__init__.py`, `backend/app/api/audit_router.py`; Test `backend/tests/test_audit_chain.py`.

**Interfaces:** Produces `audit.append(event_type, entity_type, entity_id, actor, payload) -> AuditEntry` and `audit.verify_chain() -> dict` — thin wrappers over `HashChain(AuditEntry, "audit")` (keeps the call sites in P2–P5 unchanged); `GET /audit/verify` (any authenticated user) returns `verify_chain()`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_audit_chain.py
import pytest
from backend.app import audit


@pytest.mark.asyncio
async def test_wrapper_appends_and_verifies(client, db, reviewer_headers):
    await audit.append("file_uploaded", "dataset", "D1", "op", {"filename": "x.csv"})
    r = await client.get("/audit/verify", headers=reviewer_headers)
    assert r.status_code == 200 and r.json()["ok"] is True
```

- [ ] **Step 2: Run to verify fail** — `ModuleNotFoundError: backend.app.audit`.

- [ ] **Step 3: Implement**

```python
# backend/app/audit/__init__.py
from backend.app.chain import HashChain
from backend.app.models import AuditEntry

_chain = HashChain(AuditEntry, "audit")   # ts_field defaults to "timestamp"


async def append(event_type, entity_type, entity_id, actor, payload: dict):
    return await _chain.append(event_type=event_type, entity_type=entity_type,
                               entity_id=entity_id, actor=actor, payload=payload)


async def verify_chain() -> dict:
    return await _chain.verify()
```

```python
# backend/app/api/audit_router.py
from fastapi import APIRouter, Depends
from backend.app.audit import verify_chain
from backend.app.auth import get_current_user

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/verify")
async def verify(_=Depends(get_current_user)):
    return await verify_chain()
```

- [ ] **Step 4: Run full backend suite** — `.venv/bin/python -m pytest backend/tests -q` — Expected: all green.
- [ ] **Step 5: Commit** `feat(backend): audit wrapper over HashChain + /audit/verify`.

---

### Task 7: Real-Mongo integration lane (hash chain + Decimal128)

**Files:** Create `backend/tests/test_integration_chain.py`; Modify `pyproject.toml` (pytest marker), `conftest.py` (real-Mongo fixture).

**Interfaces:** a `@pytest.mark.integration` test, skipped unless `LVC_TEST_MONGODB_URI` is set, that binds Beanie to the **real docker Mongo**, appends entries, verifies the chain **survives a real BSON round-trip** (the case mongomock can't catch: ms-truncated datetime + Decimal128), and stores/reads a `Decimal` loan field intact.

- [ ] **Step 1: Write the test** — fixture `real_db` connects `AsyncIOMotorClient(os.environ["LVC_TEST_MONGODB_URI"])` to a scratch db, `init_db`, cleans up. Test: append 3 audit entries via `HashChain`, reload, `verify()["ok"] is True`; insert a `Loan(original_principal=Decimal("123.45"))`, reload, assert it's `Decimal("123.45")`.
- [ ] **Step 2: Run** with `LVC_TEST_MONGODB_URI=mongodb://localhost:27017 pytest -m integration` against `docker compose up mongo`; without the env it's skipped.
- [ ] **Step 3: Commit** `test(backend): real-Mongo integration lane for chain + Decimal128`.

Register the marker in `[tool.pytest.ini_options] markers = ["integration: requires a real MongoDB (LVC_TEST_MONGODB_URI)"]`.

---

## Self-Review

**1. Spec coverage:** §2 stack (FastAPI/Motor/Beanie/JWT) → T1,T2,T4; §3 roles (3 exact) → T4 `require_role`; §5 all 8 collections (+`Counter`) + indexes → T2; §5 users seed → T3; §9 hash chain formula + `/audit/verify` → T5,T6; §11 `POST /auth/login`, `GET /audit/verify` → T4,T6. Endpoints owned by later plans are intentionally out of P1.

**Review fixes folded in:** 1a (stable `ts_iso`, datetime out of hash) → T5 + `test_ts_iso_is_hashed_not_datetime`; 1b (atomic `next_seq` via `Counter`) → T5; 1c (VerifiedRecord `seq` ordering) → T2 model (chain reused by P3) ; #5 (lifespan init/seed) → T1; #7 (OAuth2 form login) → T4; real-Mongo lane (Decimal128 + chain) → T7. The shared `HashChain` (T5) is the single implementation both chains use.

**2. Placeholder scan:** none — every model field is enumerated from §5; router stubs are created in T1 and filled in T4/T6; `HashChain`/`append_many` are fully specified.

**3. Type/name consistency:** `create_app` (T1) mounts `auth_router`/`audit_router` (T4/T6); `ALL_DOCUMENTS` (T2) consumed by `init_db` (T2) and later plans; `canonical_json` (T5) reused by P3 verification; `require_role`/`get_current_user` (T4) consumed by P2–P5 routers; `audit.append` signature fixed here and used verbatim in P2–P4.

## Notes for the executor
- **mongomock caveat:** if a Beanie feature (aggregation/transactions) misbehaves under `mongomock-motor`, switch that test class to the real docker `mongo` via a `LVC_MONGODB_URI` env + a `pytestmark` skip-if-unset; keep unit tests offline.
- Do **not** hardcode secrets; `jwt_secret` default is dev-only and overridden by env in P7's compose.
- `Exception` model shadows the builtin — always import as `from backend.app.models import Exception as Exc` in test/impl modules that also raise exceptions.
- Add to `conftest.py` an `auth_headers(role)` helper + `reviewer_headers`/`operator_headers`/`consumer_headers` fixtures (seed a user of that role, mint a token, return `{"Authorization": f"Bearer <tok>"}`); T6 and every later plan's API tests use them.
- **Domain-field BSON-stability** is a hard rule for anything hashed: audit `payload`s and the verified record's `canonical_data` must be plain JSON (strings/ints/lists/dicts) — never a raw `datetime`/`Decimal` — or `verify()` will break against real Mongo (the very bug 1a fixes).

**Execution deviations (found while building P1, kept for later plans):**
- **Pin `beanie>=1.26,<2`.** Beanie 2.x's index sync calls `list_collection_names(authorizedCollections=…)`, which `mongomock-motor` rejects → every offline test errors. Beanie 1.30 works with mongomock. (If we later move all tests to real Mongo we can lift the pin.)
- **`backend/app/models/types.py` `Money = Annotated[Decimal, BeforeValidator(Decimal128→Decimal)]`.** Beanie stores `Decimal` as BSON `Decimal128`; pydantic v2 won't re-validate that back into a `Decimal` field on read. All `Decimal` model fields (Loan money fields, and any added later) must use `Money`, not bare `Decimal`.
