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


@pytest_asyncio.fixture
async def auth_headers(db):
    """Factory: seed a user of `role` (idempotent) and return bearer headers."""
    async def _make(role, username=None):
        from backend.app.models import User
        from backend.app.auth import hash_password, make_token
        username = username or f"{role}_user"
        if await User.find_one(User.username == username) is None:
            await User(username=username, role=role, display_name=role,
                       password_hash=hash_password("pw")).insert()
        return {"Authorization": f"Bearer {make_token(username, role)}"}
    return _make


@pytest_asyncio.fixture
async def reviewer_headers(auth_headers):
    return await auth_headers("reviewer")


@pytest_asyncio.fixture
async def operator_headers(auth_headers):
    return await auth_headers("data_operator")


@pytest_asyncio.fixture
async def consumer_headers(auth_headers):
    return await auth_headers("data_consumer")
