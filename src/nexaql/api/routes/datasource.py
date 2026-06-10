# Copyright (c) 2026-present NexaQL Contributors
"""Data source management — connect databases and auto-generate ontologies.

Endpoints:
    POST /api/datasource/test     — test connection, return table list
    POST /api/datasource/connect  — generate ontology from selected tables, save, reload
    GET  /api/datasource/current  — current datasource info
"""

from __future__ import annotations

import os
import traceback
from typing import Any, Optional

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from nexaql.api.deps import _adapter_cache, get_config, get_ontology
from nexaql.ontology.generator import OntologyGenerator, TableInfo
from nexaql.ontology.writer import save_ontology

router = APIRouter(tags=["datasource"])


# ── Request / response models ─────────────────────────────────────────────


class TestConnectionRequest(BaseModel):
    connection_url: str
    """Database connection URL (postgresql://, mysql://, or DuckDB file path)."""
    schema_name: str = "public"
    """Schema to introspect (default: public)."""


class ConnectRequest(BaseModel):
    connection_url: str
    schema_name: str = "public"
    include_tables: Optional[list[str]] = None
    """If set, only include these tables in the ontology."""
    exclude_tables: Optional[list[str]] = None
    """Tables to exclude from the ontology."""
    domain: str = "auto_generated"
    """Domain name for the ontology (e.g. 'ecommerce', 'hr')."""
    description: str = ""
    """Human-readable description of this data source."""
    detect_enums: bool = True
    detect_pii: bool = True
    output_path: Optional[str] = None
    """Where to save the ontology YAML. Default: ontologies/{domain}.yaml"""
    store_in_db: bool = False
    """If true, store the ontology in the connected database (nexaql_ontologies table)
    instead of a YAML file. The ontology is stored as JSONB with version history."""


# ── POST /datasource/test ─────────────────────────────────────────────────


@router.post("/datasource/test")
async def test_connection(req: TestConnectionRequest) -> JSONResponse:
    """Test a database connection and return the list of tables.

    Returns table names, column counts, row count estimates, and primary keys.
    Does NOT generate an ontology or modify any state.
    """
    try:
        gen = OntologyGenerator(connection_url=req.connection_url)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)

    try:
        tables, foreign_keys = await gen.introspect(
            schema=req.schema_name,
        )
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

    # Build table summaries
    table_list = []
    for t in tables:
        columns = [
            {
                "name": c.name,
                "type": c.data_type,
                "is_primary_key": c.is_primary_key,
                "is_nullable": c.is_nullable,
                "is_pii": False,  # Will be detected during generation
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
            "comment": t.comment,
        })

    # FK summary
    fk_list = [
        {
            "from": f"{fk.from_table}.{fk.from_column}",
            "to": f"{fk.to_table}.{fk.to_column}",
            "constraint": fk.constraint_name,
        }
        for fk in foreign_keys
    ]

    return JSONResponse({
        "status": "connected",
        "db_type": gen._db_type,
        "schema": req.schema_name,
        "tables": table_list,
        "table_count": len(table_list),
        "foreign_keys": fk_list,
        "fk_count": len(fk_list),
    })


# ── POST /datasource/connect ──────────────────────────────────────────────


@router.post("/datasource/connect")
async def connect_datasource(req: ConnectRequest) -> JSONResponse:
    """Generate an ontology from the database schema and activate it.

    Steps:
    1. Introspect the database (tables, columns, FKs, enums)
    2. Generate a NexaQL ontology
    3. Save to YAML
    4. Reload the ontology (hot-swap)
    5. Clear adapter cache so new queries use this datasource

    The generated ontology is immediately available for querying.
    """
    try:
        gen = OntologyGenerator(connection_url=req.connection_url)
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
        return JSONResponse({
            "error": f"Missing database driver: {e}",
        }, status_code=400)
    except Exception as e:
        return JSONResponse({
            "error": f"Ontology generation failed: {e}",
            "details": traceback.format_exc().split("\n")[-3:],
        }, status_code=500)

    # Determine output path
    output_path = req.output_path
    if not output_path:
        os.makedirs("ontologies", exist_ok=True)
        output_path = f"ontologies/{req.domain}.yaml"

    # Patch datasource URL into the ontology
    # The generator creates a stub datasource; update it with the actual URL
    if ontology.datasources and "default" in ontology.datasources:
        ds = ontology.datasources["default"]
        if hasattr(ds, "url"):
            ds.url = req.connection_url  # type: ignore[attr-defined]
        elif hasattr(ds, "path"):
            ds.path = req.connection_url  # type: ignore[attr-defined]

    # Save ontology — to database (JSONB) or YAML file
    import os as _os
    store_backend = _os.environ.get("NEXAQL_ONTOLOGY_STORE")
    stored_in_db = False

    if req.store_in_db or store_backend == "postgres":
        try:
            from nexaql.ontology.store import PostgresStore
            # Use the same database the user just connected to
            db_url = req.connection_url
            if store_backend == "postgres":
                db_url = _os.environ.get("NEXAQL_ONTOLOGY_DB", req.connection_url)
            store = PostgresStore(db_url)
            await store.save(ontology, author="datasource-wizard")
            stored_in_db = True

            # Also set env vars so subsequent loads use the store
            _os.environ["NEXAQL_ONTOLOGY_STORE"] = "postgres"
            _os.environ["NEXAQL_ONTOLOGY_DB"] = db_url
        except Exception as e:
            # If DB storage fails, fall back to YAML
            if req.store_in_db:
                return JSONResponse({
                    "error": f"Failed to save ontology to database: {e}",
                    "hint": "The nexaql_ontologies table may need to be created. Try the /api/store/migrate endpoint first.",
                }, status_code=500)
            # Otherwise silently fall back to YAML

    if not stored_in_db:
        try:
            save_ontology(ontology, output_path)
        except Exception as e:
            return JSONResponse({
                "error": f"Failed to save ontology: {e}",
            }, status_code=500)

    # Save connector + schema to bootstrap DB
    try:
        from nexaql import bootstrap as bs

        # Ensure connector exists in bootstrap DB
        connector_id = bs.save_connector(
            name=f"ds-{req.domain}",
            type=gen._db_type,
            url=req.connection_url,
        )

        # Save ontology as schema in bootstrap DB
        ontology_dict = ontology.model_dump(exclude_none=True)
        bs.save_schema(
            domain_name=req.domain,
            schema_name=req.schema_name if hasattr(req, 'schema_name') else "public",
            connector_id=connector_id,
            ontology_json=ontology_dict,
        )

        # Set as active domain
        bs.set_active_domain(req.domain)
    except Exception:
        pass  # Non-fatal — ontology is saved in DB store

    # Reload config + clear adapter/ontology caches
    try:
        from nexaql.api.deps import reload_config, invalidate_ontology_cache
        reload_config()
        _adapter_cache.clear()
        invalidate_ontology_cache()

    except Exception as e:
        # Non-fatal — ontology is saved, just not hot-reloaded
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
        "status": "connected",
        "ontology_path": output_path if not stored_in_db else None,
        "stored_in": "database" if stored_in_db else "file",
        "storage_detail": f"nexaql_ontologies table in {gen._db_type}" if stored_in_db else output_path,
        "domain": req.domain,
        "db_type": gen._db_type,
        "nodes": node_summary,
        "node_count": len(ontology.nodes),
        "total_fields": sum(len(n.fields) for n in ontology.nodes.values()),
        "total_edges": sum(len(n.edges) for n in ontology.nodes.values() if n.edges),
    })


# ── GET /datasource/current ───────────────────────────────────────────────


@router.get("/datasource/current")
async def get_current_datasource() -> JSONResponse:
    """Return info about the currently configured datasource."""
    try:
        from nexaql import bootstrap as bs
        import re

        cfg = get_config()
        ont = get_ontology()

        datasources = {}
        for name, ds in cfg.datasources.items():
            url = ds.url or ds.path or "unknown"
            if "://" in str(url):
                url = re.sub(r"://([^:]+):([^@]+)@", r"://\1:***@", str(url))
            datasources[name] = {"type": ds.type, "url": url}

        return JSONResponse({
            "active_domain": bs.get_active_domain(),
            "datasources": datasources,
            "domain": ont.domain,
            "description": ont.description,
            "node_count": len(ont.nodes),
            "nodes": list(ont.nodes.keys()),
            "source": "bootstrap_db",
        })
    except Exception as e:
        return JSONResponse({
            "status": "not_configured",
            "error": str(e),
        })
