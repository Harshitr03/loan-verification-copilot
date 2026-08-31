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
