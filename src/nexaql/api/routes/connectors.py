# Copyright (c) 2026-present NexaQL Contributors
"""Connector management — save, test, and manage named database connections.

All data is stored in the bootstrap database (~/.nexaql/nexaql.db).

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
from typing import Any, Optional

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from nexaql import bootstrap as bs
from nexaql.api.deps import _adapter_cache, get_config, reload_config
from nexaql.ontology.generator import OntologyGenerator

router = APIRouter(tags=["connectors"])


# ── Legacy compat: connectors.json fallback (read-only, for migration) ──────

CONNECTORS_FILE = os.environ.get("NEXAQL_CONNECTORS_FILE", "connectors.json")


def _load_connectors() -> dict[str, dict[str, Any]]:
    """Load saved connectors from disk (legacy, for migration only)."""
    if not os.path.exists(CONNECTORS_FILE):
        return {}
    with open(CONNECTORS_FILE) as f:
        return json.load(f)


def _mask_url(url: str) -> str:
    """Mask password in connection URL for display."""
    import re
    return re.sub(r"://([^:]+):([^@]+)@", r"://\1:***@", str(url))


def get_active_db_url() -> str | None:
    """Get the connection URL of the active connector.

    Uses bootstrap DB first, falls back to connectors.json.
    """
    # Bootstrap DB
    try:
        active_domain = bs.get_active_domain()
        if active_domain:
            schemas = bs.list_schemas(active_domain)
            if schemas:
                connector = bs.get_connector_by_id(schemas[0]["connector_id"])
                if connector and connector.get("url"):
                    return connector["url"]

        connectors = bs.list_connectors()
        if connectors:
            return connectors[0].get("url")
    except Exception:
        pass

    # Legacy fallback
    legacy = _load_connectors()
    if legacy:
        first = next(iter(legacy.values()))
        return first.get("connection_url")
    return None


# ── API Key helpers ──────────────────────────────────────────────────────────


def _mask_key(key: str) -> str:
    """Mask an API key for display, showing only last 4 characters."""
    if len(key) <= 8:
        return "***" + key[-2:]
    return key[:4] + "..." + key[-4:]


def get_api_key(provider: str) -> str | None:
    """Get the API key for a provider.

    Checks bootstrap DB first, then falls back to environment variables.
    """
    return bs.get_api_key(provider)


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
    """Database schema to introspect (e.g. 'public', 'main')."""
    output_schema_name: Optional[str] = None
    """Name to save the schema under in the bootstrap DB. Defaults to connector_name."""
    replace: bool = True
    """If true, replace existing schema with the same name. If false, reject duplicates."""
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
    connectors = bs.list_connectors()
    result = []
    for c in connectors:
        result.append({
            "id": c["id"],
            "name": c["name"],
            "connection_url_masked": _mask_url(c.get("url", "")),
            "db_type": c.get("type", "unknown"),
            "description": "",
            "created_at": c.get("created_at", ""),
        })
    return JSONResponse({"connectors": result, "count": len(result)})


# ── POST /connectors ────────────────────────────────────────────────────


@router.post("/connectors")
async def save_connector(req: SaveConnectorRequest) -> JSONResponse:
    """Save a new named connector. Tests the connection first."""
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

    # Save to bootstrap DB
    connector_id = bs.save_connector(
        name=name,
        type=gen._db_type,
        url=req.connection_url,
    )

    return JSONResponse({
        "status": "saved",
        "id": connector_id,
        "name": name,
        "db_type": gen._db_type,
        "table_count": len(tables),
        "connection_url_masked": _mask_url(req.connection_url),
    })


# ── POST /connectors/test ───────────────────────────────────────────────


@router.post("/connectors/test")
async def test_connector(req: TestConnectorRequest) -> JSONResponse:
    """Test a saved connector by name."""
    connector = bs.get_connector(req.name)
    if connector is None:
        return JSONResponse({"error": f"Connector '{req.name}' not found"}, status_code=404)

    try:
        gen = OntologyGenerator(connection_url=connector["url"])
        tables, fks = await gen.introspect(schema="public")
    except Exception as e:
        return JSONResponse({
            "status": "failed",
            "error": str(e),
        }, status_code=400)

    return JSONResponse({
        "status": "ok",
        "table_count": len(tables),
        "fk_count": len(fks),
    })


# ── DELETE /connectors/{name} ───────────────────────────────────────────


@router.delete("/connectors/{name}")
async def delete_connector(name: str) -> JSONResponse:
    """Delete a saved connector. Fails if referenced by schemas."""
    try:
        deleted = bs.delete_connector(name)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=409)

    if not deleted:
        return JSONResponse({"error": f"Connector '{name}' not found"}, status_code=404)

    return JSONResponse({"status": "deleted", "name": name})


# ── POST /connectors/{name}/introspect ──────────────────────────────────


@router.post("/connectors/{name}/introspect")
async def introspect_connector(name: str, req: IntrospectRequest | None = None) -> JSONResponse:
    """Introspect tables from a saved connector."""
    connector = bs.get_connector(name)
    if connector is None:
        return JSONResponse({"error": f"Connector '{name}' not found"}, status_code=404)

    schema = req.schema_name if req else "public"

    # DuckDB uses 'main' as its default schema, not 'public'
    db_type = connector.get("type", "")
    if db_type == "duckdb" and schema == "public":
        schema = "main"

    try:
        gen = OntologyGenerator(connection_url=connector["url"])
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

    Saves the ontology into the bootstrap DB (schema-per-ontology model)
    and also into the target database's nexaql_ontologies table for backward compat.
    """
    connector = bs.get_connector(req.connector_name)
    if connector is None:
        return JSONResponse(
            {"error": f"Connector '{req.connector_name}' not found"},
            status_code=404,
        )

    connection_url = connector["url"]
    connector_id = connector["id"]

    try:
        gen = OntologyGenerator(connection_url=connection_url)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)

    # DuckDB uses 'main' as its default schema, not 'public'
    gen_schema = req.schema_name
    if gen._db_type == "duckdb" and gen_schema == "public":
        gen_schema = "main"

    # Generate ontology
    try:
        description = req.description or f"Auto-generated from {gen._db_type} database"
        ontology = await gen.generate(
            schema=gen_schema,
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

    # Save to bootstrap DB
    save_name = req.output_schema_name or req.connector_name
    try:
        # Check for duplicate when replace=False (i.e. "Add Schema")
        if not req.replace:
            existing = bs.get_schema(req.domain, save_name)
            if existing:
                return JSONResponse(
                    {"error": f"Schema '{save_name}' already exists in domain '{req.domain}'. Use a different name or regenerate the existing schema."},
                    status_code=409,
                )

        ontology_dict = ontology.model_dump(exclude_none=True)

        # Bootstrap default roles and access functions if not already present
        if "roles" not in ontology_dict or not ontology_dict["roles"]:
            ontology_dict["roles"] = {
                "admin": {"description": "Full access to all data"},
                "analyst": {"description": "Read-only access for reporting and analytics"},
                "manager": {"description": "Access scoped to their department or region"},
            }
        if "access_functions" not in ontology_dict or not ontology_dict["access_functions"]:
            ontology_dict["access_functions"] = {
                "owns_record": {
                    "description": "User owns the record (created_by or user_id matches)",
                    "sql": "{field} = {user.id}",
                    "requires": ["id"],
                },
                "same_department": {
                    "description": "User belongs to the same department",
                    "sql": "{field} = {user.department}",
                    "requires": ["department"],
                },
                "same_region": {
                    "description": "User is in the same region",
                    "sql": "{field} = {user.region}",
                    "requires": ["region"],
                },
            }

        bs.save_schema(
            domain_name=req.domain,
            schema_name=save_name,
            connector_id=connector_id,
            ontology_json=ontology_dict,
        )

        # Update domain description
        domain = bs.get_domain(req.domain)
        if domain:
            bs._get_conn().execute(
                "UPDATE domains SET description = ? WHERE name = ?",
                [description, req.domain],
            )

        # Set as active domain
        bs.set_active_domain(req.domain)
    except Exception as e:
        return JSONResponse({
            "error": f"Failed to save ontology to bootstrap DB: {e}",
            "details": traceback.format_exc().split("\n")[-3:],
        }, status_code=500)

    # Also save to the target database for backward compat
    try:
        from nexaql.ontology.store import get_store, reset_store
        reset_store()
        if connection_url.startswith("postgresql"):
            from nexaql.ontology.store import PostgresStore
            store = PostgresStore(connection_url)
        else:
            from nexaql.ontology.store import DuckDBStore
            store = DuckDBStore(connection_url)
        await store.save(ontology, author="admin-generate")
    except Exception:
        pass  # Non-fatal — bootstrap DB is the source of truth

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
        "stored_in": "bootstrap_db",
        "storage_detail": f"~/.nexaql/nexaql.db + {gen._db_type}",
        "domain": req.domain,
        "db_type": gen._db_type,
        "connector_name": req.connector_name,
        "connector_id": connector_id,
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
    keys = bs.list_api_keys()
    result = []
    for k in keys:
        result.append({
            "provider": k["provider"],
            "name": k.get("name", k["provider"]),
            "key_masked": _mask_key(k.get("key", "")),
            "created_at": k.get("created_at", ""),
            "is_active": True,
        })
    return JSONResponse({"api_keys": result})


@router.post("/api-keys")
async def save_api_key(req: SaveApiKeyRequest) -> JSONResponse:
    """Save or update an API key."""
    if not req.provider.strip() or not req.key.strip():
        return JSONResponse({"error": "Provider and key are required"}, status_code=400)

    provider_key = req.provider.strip().lower()

    # Save to bootstrap DB
    bs.save_api_key(provider=provider_key, name=req.name.strip(), key=req.key.strip())

    # Inject into environment so LLM picks it up immediately
    env_map = {
        "anthropic": "ANTHROPIC_API_KEY",
        "openai": "OPENAI_API_KEY",
        "openrouter": "OPENROUTER_API_KEY",
        "google": "GOOGLE_API_KEY",
        "cohere": "COHERE_API_KEY",
        "meta": "META_API_KEY",
    }
    env_var = env_map.get(provider_key)
    if env_var:
        os.environ[env_var] = req.key.strip()

    # Auto-configure LLM provider/model when a cloud key is saved
    try:
        from nexaql.chat.llm import DEFAULT_MODELS

        llm_cfg = bs.get_active_llm_config()
        current_provider = llm_cfg["provider"] if llm_cfg else ""
        current_model = llm_cfg["model"] if llm_cfg else ""

        new_provider = current_provider
        new_model = current_model

        if provider_key == "openrouter":
            new_provider = "openrouter"
            if not current_model or current_model.startswith("qwen3:"):
                new_model = "anthropic/claude-sonnet-4-6"
        elif provider_key == "anthropic":
            new_provider = "anthropic"
            if not current_model or not current_model.startswith("claude"):
                new_model = "claude-sonnet-4-6"
        elif provider_key == "openai":
            new_provider = "openai"
            if not current_model or not current_model.startswith("gpt"):
                new_model = "gpt-4o"
        elif provider_key == "meta":
            new_provider = "meta"
            if not current_model or not current_model.startswith("muse"):
                new_model = "muse-spark-1.1"

        if new_provider != current_provider or new_model != current_model:
            bs.save_llm_config(
                provider=new_provider,
                model=new_model,
                generation_mode="intent",
            )
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
    deleted = bs.delete_api_key(provider)
    if not deleted:
        return JSONResponse({"error": f"API key for '{provider}' not found"}, status_code=404)

    # Remove from environment
    env_map = {
        "anthropic": "ANTHROPIC_API_KEY",
        "openai": "OPENAI_API_KEY",
        "openrouter": "OPENROUTER_API_KEY",
        "google": "GOOGLE_API_KEY",
        "cohere": "COHERE_API_KEY",
        "meta": "META_API_KEY",
    }
    env_var = env_map.get(provider.lower())
    if env_var and env_var in os.environ:
        del os.environ[env_var]

    reload_config()

    return JSONResponse({"status": "deleted", "provider": provider})


# ── LLM Config endpoints ──────────────────────────────────────────────────


@router.get("/llm-config")
async def get_llm_config() -> JSONResponse:
    """Get current LLM provider and model configuration."""
    cfg = bs.get_active_llm_config()
    if not cfg:
        return JSONResponse({"provider": "", "model": ""})
    return JSONResponse({
        "provider": cfg.get("provider", ""),
        "model": cfg.get("model", ""),
        "max_tokens": cfg.get("max_tokens", 4096),
        "generation_mode": cfg.get("generation_mode", "intent"),
    })


class UpdateLLMConfigRequest(BaseModel):
    model: str
    provider: Optional[str] = None


@router.put("/llm-config")
async def update_llm_config(req: UpdateLLMConfigRequest) -> JSONResponse:
    """Update the active LLM provider and model."""
    if not req.model.strip():
        return JSONResponse({"error": "Model is required"}, status_code=400)

    cfg = bs.get_active_llm_config()
    provider = req.provider.strip() if req.provider and req.provider.strip() else (cfg["provider"] if cfg else "anthropic")

    bs.save_llm_config(
        provider=provider,
        model=req.model.strip(),
        generation_mode=cfg.get("generation_mode", "intent") if cfg else "intent",
    )

    reload_config()
    try:
        from nexaql.chat.llm import invalidate_client_cache
        invalidate_client_cache()
    except Exception:
        pass

    return JSONResponse({"status": "updated", "provider": provider, "model": req.model.strip()})
