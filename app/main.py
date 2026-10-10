"""FastAPI application factory and entry point."""

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .auth import router as auth_router
from .config import database_path
from .conversations import router as conversations_router
from .db import init_db
from .users import router as users_router
from .ws import router as ws_router

# Vite dev-server origins allowed to call the API during development.
_DEV_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]


def create_app(db_path: str | None = None) -> FastAPI:
    """Build the FastAPI app. `db_path` overrides the configured database (used by tests)."""
    resolved_path = db_path or os.environ.get("MESSAIN_DATABASE", database_path())

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        init_db(resolved_path)
        yield

    app = FastAPI(title="Messain API", version="1.0.0", lifespan=lifespan)
    app.state.database_path = resolved_path

    app.add_middleware(
        CORSMiddleware,
        allow_origins=_DEV_ORIGINS,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(auth_router)
    app.include_router(users_router)
    app.include_router(conversations_router)
    app.include_router(ws_router)

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    # Serve the built frontend when present, so `uvicorn` alone can run the whole app.
    dist_dir = Path(__file__).resolve().parents[1] / "frontend" / "dist"
    if dist_dir.is_dir():
        app.mount("/", StaticFiles(directory=dist_dir, html=True), name="frontend")

    return app


app = create_app()
