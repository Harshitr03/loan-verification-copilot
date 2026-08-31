from fastapi import FastAPI
from backend.app.lifespan import lifespan


def create_app() -> FastAPI:
    app = FastAPI(title="Loan Verification Copilot API", lifespan=lifespan)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    from backend.app.api.auth_router import router as auth_router
    from backend.app.api.audit_router import router as audit_router
    from backend.app.api.datasets import router as datasets_router
    from backend.app.api.exceptions import router as exceptions_router
    from backend.app.api.verify import router as verify_router
    from backend.app.api.ai import router as ai_router
    from backend.app.api.public import router as public_router
    app.include_router(auth_router)
    app.include_router(audit_router)
    app.include_router(datasets_router)
    app.include_router(exceptions_router)
    app.include_router(verify_router)
    app.include_router(ai_router)
    app.include_router(public_router)
    return app
