from contextlib import asynccontextmanager
from motor.motor_asyncio import AsyncIOMotorClient
from backend.app.config import get_settings


@asynccontextmanager
async def lifespan(app):
    # Lazy imports: db/seed modules land in Tasks 2 & 3. Keeping them inside the
    # function lets `create_app()` import cleanly from Task 1 on, and the body only
    # runs at real startup (never under httpx ASGITransport, which skips lifespan).
    from backend.app.db import init_db
    from backend.app.seed import seed_users

    s = get_settings()
    client = AsyncIOMotorClient(s.mongodb_uri)
    await init_db(client, s.mongodb_db)     # bind Beanie to the REAL mongo on boot
    try:
        await seed_users()                  # idempotent; no-op if users.json absent
    except FileNotFoundError:
        pass
    try:
        yield
    finally:
        client.close()                      # release the Motor client on shutdown
