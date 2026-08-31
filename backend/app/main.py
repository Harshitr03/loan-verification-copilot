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
