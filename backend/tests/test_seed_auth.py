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
    await User(username="rev2", role="reviewer", display_name="R",
               password_hash=bcrypt.hashpw(b"a", bcrypt.gensalt()).decode()).insert()
    r = await client.post("/auth/login", data={"username": "rev2", "password": "wrong"})
    assert r.status_code == 401
