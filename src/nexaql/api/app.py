# Copyright (c) 2026-present NexaQL Contributors
"""FastAPI application factory for NexaQL."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from nexaql.api.deps import get_config
from nexaql.api.routes import chat, execute, ontology, suggest, validate


def create_app() -> FastAPI:
    """Build and return the FastAPI application instance."""
    cfg = get_config()

    app = FastAPI(
        title="NexaQL",
        description="A GraphQL-inspired query language for any structured data",
        version="0.1.0",
    )

    # ── CORS ────────────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.server.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── API routes ──────────────────────────────────────────────────────────
    app.include_router(execute.router, prefix="/api")
    app.include_router(validate.router, prefix="/api")
    app.include_router(ontology.router, prefix="/api")
    app.include_router(suggest.router, prefix="/api")
    app.include_router(chat.router, prefix="/api")

    # ── Health check ────────────────────────────────────────────────────────
    @app.get("/api/health")
    async def health() -> JSONResponse:
        return JSONResponse({"status": "ok"})

    # ── Serve frontend static files ───────────────────────────────────────
    # Check bundled static dir first (pip install), then local frontend/dist (dev)
    bundled_static = Path(__file__).parent.parent / "static"
    local_dist = Path(os.getcwd()) / "frontend" / "dist"

    static_dir = bundled_static if bundled_static.is_dir() else local_dist
    if static_dir.is_dir():
        app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="frontend")

    return app
