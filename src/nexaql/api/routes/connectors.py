# Copyright (c) 2026-present NexaQL Contributors
"""Connector management — save, test, and manage named database connections.

Endpoints:
    GET    /api/connectors              — list all saved connectors
    POST   /api/connectors              — save a new connector
    POST   /api/connectors/test         — test a saved connector by name
    DELETE /api/connectors/{name}       — delete a connector
    POST   /api/connectors/{name}/introspect — introspect tables from a saved connector
    POST   /api/generate-ontology       — generate ontology from a saved connector
"""

from __future__ import annotations

import json
import os
import traceback
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from nexaql.api.deps import _adapter_cache, get_config, reload_config
from nexaql.ontology.generator import OntologyGenerator

router = APIRouter(tags=["connectors"])

# ── Connector storage (JSON file) ─────────────────────────────────────────

CONNECTORS_FILE = os.environ.get("NEXAQL_CONNECTORS_FILE", "connectors.json")


def _load_connectors() -> dict[str, dict[str, Any]]:
    """Load saved connectors from disk."""
    if not os.path.exists(CONNECTORS_FILE):
        return {}
    with open(CONNECTORS_FILE) as f:
        return json.load(f)


def _save_connectors(connectors: dict[str, dict[str, Any]]) -> None:
    """Persist connectors to disk."""
    with open(CONNECTORS_FILE, "w") as f:
        json.dump(connectors, f, indent=2, default=str)


def _mask_url(url: str) -> str:
    """Mask password in connection URL for display."""
    import re
    return re.sub(r"://([^:]+):([^@]+)@", r"://\1:***@", str(url))


def get_active_db_url() -> str | None:
    """Get the connection URL of the first (or active) saved connector.

    This is used by the ontology store to know which DB to read/write from.
    Returns None if no connectors are saved.
    """
    connectors = _load_connectors()
    if not connectors:
        return None
    # Return the first connector's URL
    first = next(iter(connectors.values()))
    return first.get("connection_url")


# ── API Key storage (JSON file) ──────────────────────────────────────────

API_KEYS_FILE = os.environ.get("NEXAQL_API_KEYS_FILE", "api_keys.json")


def _load_api_keys() -> dict[str, dict[str, Any]]:
    """Load saved API keys from disk."""
    if not os.path.exists(API_KEYS_FILE):
        return {}
    with open(API_KEYS_FILE) as f:
        return json.load(f)


def _save_api_keys(keys: dict[str, dict[str, Any]]) -> None:
    """Persist API keys to disk."""
    with open(API_KEYS_FILE, "w") as f:
        json.dump(keys, f, indent=2, default=str)


def _mask_key(key: str) -> str:
    """Mask an API key for display, showing only last 4 characters."""
    if len(key) <= 8:
        return "***" + key[-2:]
    return key[:4] + "..." + key[-4:]


def get_api_key(provider: str) -> str | None:
    """Get the API key for a provider. Used by chat/LLM routes.

    Checks saved keys first, then falls back to environment variables.
    """
    keys = _load_api_keys()
    if provider in keys:
        return keys[provider].get("key")
    # Fallback: check common env vars
    env_map = {
        "anthropic": "ANTHROPIC_API_KEY",
        "openai": "OPENAI_API_KEY",
        "openrouter": "OPENROUTER_API_KEY",
        "google": "GOOGLE_API_KEY",
        "cohere": "COHERE_API_KEY",
    }
    env_var = env_map.get(provider.lower())
    if env_var:
        return os.environ.get(env_var)
    return None


# ── Request / response models ─────────────────────────────────────────────


class SaveConnectorRequest(BaseModel):
    name: str
    """Unique name for this connector (e.g. 'production-pg', 'analytics-db')."""
    connection_url: str
    """Database connection URL (postgresql://, mysql://, or DuckDB file path)."""
    schema_name: str = "public"
    """Schema to introspect (default: public)."""
    description: str = ""
    """Human-readable description."""


class TestConnectorRequest(BaseModel):
    name: str
    """Name of the saved connector to test."""


class IntrospectRequest(BaseModel):
    schema_name: str = "public"
    """Schema to introspect."""


class GenerateOntologyRequest(BaseModel):
    connector_name: str
    """Name of the saved connector to use."""
    schema_name: str = "public"
    """Schema to introspect."""
    include_tables: Optional[list[str]] = None
    """If set, only include these tables."""
    exclude_tables: Optional[list[str]] = None
    """Tables to exclude."""
    domain: str = "auto_generated"
    """Domain name for the ontology."""
    description: str = ""
    """Human-readable description of this data source."""
    detect_enums: bool = True
    detect_pii: bool = True


# ── GET /connectors ──────────────────────────────────────────────────────


@router.get("/connectors")
async def list_connectors() -> JSONResponse:
    """List all saved connectors (URLs are masked)."""
    connectors = _load_connectors()
    result = []
    for name, data in connectors.items():
        result.append({
            "name": name,
            "connection_url_masked": _mask_url(data["connection_url"]),
            "db_type": data.get("db_type", "unknown"),
            "schema_name": data.get("schema_name", "public"),
            "description": data.get("description", ""),
            "created_at": data.get("created_at", ""),
            "last_tested": data.get("last_tested"),
            "last_test_ok": data.get("last_test_ok"),
        })
    return JSONResponse({"connectors": result, "count": len(result)})


# ── POST /connectors ────────────────────────────────────────────────────


@router.post("/connectors")
async def save_connector(req: SaveConnectorRequest) -> JSONResponse:
    """Save a new named connector. Tests the connection first."""
    # Validate name
    name = req.name.strip()
    if not name:
        return JSONResponse({"error": "Connector name is required"}, status_code=400)
    if "/" in name or "\\" in name:
        return JSONResponse({"error": "Invalid connector name"}, status_code=400)

    # Test connection
    try:
        gen = OntologyGenerator(connection_url=req.connection_url)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)

    try:
        tables, _ = await gen.introspect(schema=req.schema_name)
    except ImportError as e:
        return JSONResponse({
            "error": f"Missing database driver: {e}",
            "hint": "Install the required driver: pip install asyncpg (PostgreSQL) or pip install aiomysql (MySQL)",
        }, status_code=400)
    except Exception as e:
        return JSONResponse({
            "error": f"Connection failed: {e}",
            "details": traceback.format_exc().split("\n")[-3:],
        }, status_code=400)

    # Save
    connectors = _load_connectors()
    now = datetime.now(timezone.utc).isoformat()
    connectors[name] = {
        "connection_url": req.connection_url,
        "db_type": gen._db_type,
        "schema_name": req.schema_name,
        "description": req.description,
        "table_count": len(tables),
        "created_at": now,
        "last_tested": now,
        "last_test_ok": True,
    }
    _save_connectors(connectors)

    return JSONResponse({
        "status": "saved",
        "name": name,
        "db_type": gen._db_type,
        "table_count": len(tables),
        "connection_url_masked": _mask_url(req.connection_url),
    })


# ── POST /connectors/test ───────────────────────────────────────────────


@router.post("/connectors/test")
async def test_connector(req: TestConnectorRequest) -> JSONResponse:
    """Test a saved connector by name."""
    connectors = _load_connectors()
    if req.name not in connectors:
        return JSONResponse({"error": f"Connector '{req.name}' not found"}, status_code=404)

    data = connectors[req.name]
    try:
        gen = OntologyGenerator(connection_url=data["connection_url"])
        tables, fks = await gen.introspect(schema=data.get("schema_name", "public"))
    except Exception as e:
        # Update test status
        data["last_tested"] = datetime.now(timezone.utc).isoformat()
        data["last_test_ok"] = False
        _save_connectors(connectors)
        return JSONResponse({
            "status": "failed",
            "error": str(e),
        }, status_code=400)

    # Update test status
    data["last_tested"] = datetime.now(timezone.utc).isoformat()
    data["last_test_ok"] = True
    data["table_count"] = len(tables)
    _save_connectors(connectors)

    return JSONResponse({
        "status": "ok",
        "table_count": len(tables),
        "fk_count": len(fks),
    })


# ── DELETE /connectors/{name} ───────────────────────────────────────────


@router.delete("/connectors/{name}")
async def delete_connector(name: str) -> JSONResponse:
    """Delete a saved connector."""
    connectors = _load_connectors()
    if name not in connectors:
        return JSONResponse({"error": f"Connector '{name}' not found"}, status_code=404)

    del connectors[name]
    _save_connectors(connectors)
    return JSONResponse({"status": "deleted", "name": name})


# ── POST /connectors/{name}/introspect ──────────────────────────────────


@router.post("/connectors/{name}/introspect")
async def introspect_connector(name: str, req: IntrospectRequest | None = None) -> JSONResponse:
    """Introspect tables from a saved connector."""
    connectors = _load_connectors()
    if name not in connectors:
        return JSONResponse({"error": f"Connector '{name}' not found"}, status_code=404)

    data = connectors[name]
    schema = req.schema_name if req else data.get("schema_name", "public")

    try:
        gen = OntologyGenerator(connection_url=data["connection_url"])
        tables, foreign_keys = await gen.introspect(schema=schema)
    except Exception as e:
        return JSONResponse({
            "error": f"Introspection failed: {e}",
        }, status_code=400)

    table_list = []
    for t in tables:
        columns = [
            {
                "name": c.name,
                "type": c.data_type,
                "is_primary_key": c.is_primary_key,
                "is_nullable": c.is_nullable,
            }
            for c in t.columns
        ]
        table_list.append({
            "name": t.name,
            "schema": t.schema_name,
            "columns": columns,
            "column_count": len(t.columns),
            "primary_key": t.primary_key,
            "row_count_estimate": t.row_count_estimate,
        })

    fk_list = [
        {
            "from": f"{fk.from_table}.{fk.from_column}",
            "to": f"{fk.to_table}.{fk.to_column}",
            "constraint": fk.constraint_name,
        }
        for fk in foreign_keys
    ]

    return JSONResponse({
        "status": "ok",
        "db_type": gen._db_type,
        "schema": schema,
        "tables": table_list,
        "table_count": len(table_list),
        "foreign_keys": fk_list,
        "fk_count": len(fk_list),
    })


# ── POST /generate-ontology ─────────────────────────────────────────────


@router.post("/generate-ontology")
async def generate_ontology(req: GenerateOntologyRequest) -> JSONResponse:
    """Generate an ontology from a saved connector.

    This is the decoupled ontology generation endpoint. It uses a saved
    connector (by name) rather than a raw connection URL.
    """
    connectors = _load_connectors()
    if req.connector_name not in connectors:
        return JSONResponse(
            {"error": f"Connector '{req.connector_name}' not found"},
            status_code=404,
        )

    conn_data = connectors[req.connector_name]
    connection_url = conn_data["connection_url"]

    try:
        gen = OntologyGenerator(connection_url=connection_url)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)

    # Generate ontology
    try:
        description = req.description or f"Auto-generated from {gen._db_type} database"
        ontology = await gen.generate(
            schema=req.schema_name,
            domain=req.domain,
            description=description,
            include_tables=req.include_tables,
            exclude_tables=req.exclude_tables,
            detect_enums=req.detect_enums,
            detect_pii=req.detect_pii,
        )
    except ImportError as e:
        return JSONResponse({"error": f"Missing database driver: {e}"}, status_code=400)
    except Exception as e:
        return JSONResponse({
            "error": f"Ontology generation failed: {e}",
            "details": traceback.format_exc().split("\n")[-3:],
        }, status_code=500)

    # Patch datasource URL
    if ontology.datasources and "default" in ontology.datasources:
        ds = ontology.datasources["default"]
        if hasattr(ds, "url"):
            ds.url = connection_url
        elif hasattr(ds, "path"):
            ds.path = connection_url

    # Save ontology to the database (always DB, no YAML files)
    try:
        from nexaql.ontology.store import get_store, reset_store
        reset_store()  # clear cached store since we may have a new connection
        if connection_url.startswith("postgresql"):
            from nexaql.ontology.store import PostgresStore
            store = PostgresStore(connection_url)
        else:
            from nexaql.ontology.store import DuckDBStore
            store = DuckDBStore(connection_url)
        await store.save(ontology, author="admin-generate")
    except Exception as e:
        return JSONResponse({
            "error": f"Failed to save ontology to database: {e}",
            "details": traceback.format_exc().split("\n")[-3:],
        }, status_code=500)

    # Update nexaql.yaml config — set datasource so queries work
    try:
        import yaml as _yaml
        config_path = os.environ.get("NEXAQL_CONFIG", "nexaql.yaml")
        with open(config_path) as f:
            raw_config = _yaml.safe_load(f) or {}

        # Set active domain (used by deps.get_ontology to know which domain to load)
        raw_config["ontology"] = {"domain": req.domain}
        raw_config["datasources"] = {
            "default": {
                "type": gen._db_type,
                **({"url": connection_url} if gen._db_type != "duckdb" else {"path": connection_url}),
            }
        }

        with open(config_path, "w") as f:
            f.write("# NexaQL configuration — updated by Admin\n")
            _yaml.dump(raw_config, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
    except Exception:
        pass

    # Reload config + clear caches
    try:
        from nexaql.api.deps import invalidate_ontology_cache
        reload_config()
        _adapter_cache.clear()
        invalidate_ontology_cache()
    except Exception:
        pass

    # Build summary
    node_summary = {}
    for name, node in ontology.nodes.items():
        node_summary[name] = {
            "table": node.table or name,
            "field_count": len(node.fields),
            "edge_count": len(node.edges) if node.edges else 0,
            "fields": list(node.fields.keys()),
            "edges": list(node.edges.keys()) if node.edges else [],
        }

    return JSONResponse({
        "status": "generated",
        "stored_in": "database",
        "storage_detail": f"nexaql_ontologies table in {gen._db_type}",
        "domain": req.domain,
        "db_type": gen._db_type,
        "connector_name": req.connector_name,
        "nodes": node_summary,
        "node_count": len(ontology.nodes),
        "total_fields": sum(len(n.fields) for n in ontology.nodes.values()),
        "total_edges": sum(len(n.edges) for n in ontology.nodes.values() if n.edges),
    })


# ── API Key endpoints ─────────────────────────────────────────────────────


class SaveApiKeyRequest(BaseModel):
    name: str
    """Display name for this key (e.g. 'Anthropic Production', 'OpenAI Dev')."""
    provider: str
    """Provider identifier (e.g. 'anthropic', 'openai', 'google')."""
    key: str
    """The API key value."""


@router.get("/api-keys")
async def list_api_keys() -> JSONResponse:
    """List all saved API keys (values masked)."""
    keys = _load_api_keys()
    result = []
    for provider, info in keys.items():
        result.append({
            "provider": provider,
            "name": info.get("name", provider),
            "key_masked": _mask_key(info.get("key", "")),
            "created_at": info.get("created_at", ""),
            "is_active": info.get("is_active", True),
        })
    return JSONResponse({"api_keys": result})


@router.post("/api-keys")
async def save_api_key(req: SaveApiKeyRequest) -> JSONResponse:
    """Save or update an API key."""
    if not req.provider.strip() or not req.key.strip():
        return JSONResponse({"error": "Provider and key are required"}, status_code=400)

    keys = _load_api_keys()
    provider_key = req.provider.strip().lower()

    keys[provider_key] = {
        "name": req.name.strip(),
        "key": req.key.strip(),
        "provider": provider_key,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "is_active": True,
    }
    _save_api_keys(keys)

    # Inject into environment so LLM config picks it up immediately
    env_map = {
        "anthropic": "ANTHROPIC_API_KEY",
        "openai": "OPENAI_API_KEY",
        "openrouter": "OPENROUTER_API_KEY",
        "google": "GOOGLE_API_KEY",
        "cohere": "COHERE_API_KEY",
    }
    env_var = env_map.get(provider_key)
    if env_var:
        os.environ[env_var] = req.key.strip()

    # Also update nexaql.yaml to switch provider/model when a cloud key is saved
    try:
        import yaml as _yaml
        from nexaql.chat.llm import DEFAULT_MODELS
        config_path = os.environ.get("NEXAQL_CONFIG", "nexaql.yaml")
        if os.path.exists(config_path):
            with open(config_path) as f:
                raw_config = _yaml.safe_load(f) or {}
            llm_section = raw_config.get("llm", {})
            # If saving an openrouter key, switch provider to openrouter
            if provider_key == "openrouter":
                llm_section["provider"] = "openrouter"
                llm_section["api_key"] = f"${{OPENROUTER_API_KEY}}"
                if llm_section.get("model", "").startswith("qwen3:"):
                    llm_section["model"] = DEFAULT_MODELS.get("openrouter", "qwen/qwen3-4b:free")
            raw_config["llm"] = llm_section
            with open(config_path, "w") as f:
                f.write("# NexaQL configuration — updated by Admin\n")
                _yaml.dump(raw_config, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
    except Exception:
        pass

    # Reload config + clear LLM client cache
    reload_config()
    try:
        from nexaql.chat.llm import invalidate_client_cache
        invalidate_client_cache()
    except Exception:
        pass

    return JSONResponse({
        "status": "saved",
        "provider": provider_key,
        "name": req.name.strip(),
        "key_masked": _mask_key(req.key.strip()),
    })


@router.delete("/api-keys/{provider}")
async def delete_api_key(provider: str) -> JSONResponse:
    """Delete a saved API key."""
    keys = _load_api_keys()
    if provider not in keys:
        return JSONResponse({"error": f"API key for '{provider}' not found"}, status_code=404)

    del keys[provider]
    _save_api_keys(keys)

    # Remove from environment
    env_map = {
        "anthropic": "ANTHROPIC_API_KEY",
        "openai": "OPENAI_API_KEY",
        "openrouter": "OPENROUTER_API_KEY",
        "google": "GOOGLE_API_KEY",
        "cohere": "COHERE_API_KEY",
    }
    env_var = env_map.get(provider.lower())
    if env_var and env_var in os.environ:
        del os.environ[env_var]

    reload_config()

    return JSONResponse({"status": "deleted", "provider": provider})
