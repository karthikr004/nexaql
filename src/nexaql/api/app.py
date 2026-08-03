# Copyright (c) 2026-present NexaQL Contributors
"""FastAPI application factory for NexaQL."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from fastapi import Depends

from nexaql.api.deps import get_config
from nexaql.api.middleware import require_admin
from nexaql.api.routes import admin, auth, chat, connectors, datasource, execute, ontology, store, suggest, validate


def _load_api_keys_into_env() -> None:
    """Load saved API keys into environment on startup.

    Reads from the bootstrap database (~/.nexaql/nexaql.db).
    """
    from nexaql import bootstrap as bs

    env_map = {
        "anthropic": "ANTHROPIC_API_KEY",
        "openai": "OPENAI_API_KEY",
        "openrouter": "OPENROUTER_API_KEY",
        "google": "GOOGLE_API_KEY",
        "cohere": "COHERE_API_KEY",
        "meta": "META_API_KEY",
    }
    for provider, env_var in env_map.items():
        if not os.environ.get(env_var):
            key = bs.get_api_key(provider)
            if key:
                os.environ[env_var] = key


def create_app() -> FastAPI:
    """Build and return the FastAPI application instance."""
    _load_api_keys_into_env()
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
    app.include_router(auth.router, prefix="/api")
    app.include_router(execute.router, prefix="/api")
    app.include_router(validate.router, prefix="/api")
    app.include_router(ontology.router, prefix="/api")
    app.include_router(suggest.router, prefix="/api")
    app.include_router(chat.router, prefix="/api")
    app.include_router(admin.router, prefix="/api", dependencies=[Depends(require_admin)])
    app.include_router(datasource.router, prefix="/api")
    app.include_router(connectors.router, prefix="/api")
    app.include_router(store.router, prefix="/api")

    # ── Health check ────────────────────────────────────────────────────────
    @app.get("/api/health")
    async def health() -> JSONResponse:
        return JSONResponse({"status": "ok"})

    # ── LLM status endpoint ────────────────────────────────────────────────
    @app.get("/api/llm/status")
    async def llm_status() -> JSONResponse:
        from nexaql.chat.llm import PROVIDER_BASE_URLS, check_ollama_status
        current_cfg = get_config()
        llm = current_cfg.llm
        provider = llm.provider.lower()

        result: dict = {
            "provider": provider,
            "model": llm.model,
            "base_url": llm.base_url or PROVIDER_BASE_URLS.get(provider, ""),
            "has_api_key": bool(llm.api_key),
        }

        # Check Ollama status if relevant
        if provider == "ollama":
            result["ollama"] = check_ollama_status()

        return JSONResponse(result)

    # ── Serve frontend static files ───────────────────────────────────────
    # Check bundled static dir first (pip install), then local frontend/dist (dev)
    bundled_static = Path(__file__).parent.parent / "static"
    local_dist = Path(os.getcwd()) / "frontend" / "dist"

    static_dir = bundled_static if bundled_static.is_dir() else local_dist
    if static_dir.is_dir():
        index_html = static_dir / "index.html"

        # SPA catch-all: serve index.html for client-side routes
        # Must be registered before the static mount so paths are caught
        from starlette.responses import FileResponse

        spa_paths = ["chat", "domains", "connectors", "playground", "setup", "settings", "admin", "login", "v2"]

        for _p in spa_paths:
            @app.get(f"/{_p}", name=f"spa_{_p}_root")
            async def spa_root(p=_p):
                return FileResponse(str(index_html))

            @app.get(f"/{_p}/{{rest:path}}", name=f"spa_{_p}_catchall")
            async def spa_catchall(rest: str, p=_p):
                return FileResponse(str(index_html))

        app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="frontend")

    return app
