# Copyright (c) 2026-present NexaQL Contributors
"""Ontology store API — CRUD with version history.

Replaces direct YAML file manipulation with a backend-agnostic store.
Works with both YamlStore (dev) and PostgresStore (production).

Endpoints:
    GET    /api/store/domains              — list all ontology domains
    GET    /api/store/ontology/:domain     — load active ontology
    PUT    /api/store/ontology/:domain     — save full ontology (new version)
    DELETE /api/store/ontology/:domain     — delete domain

    PUT    /api/store/ontology/:domain/node/:name  — update a single node
    POST   /api/store/ontology/:domain/node        — add a new node
    DELETE /api/store/ontology/:domain/node/:name  — delete a node

    GET    /api/store/ontology/:domain/versions     — version history
    GET    /api/store/ontology/:domain/version/:id  — load a specific version
    POST   /api/store/ontology/:domain/rollback/:id — rollback to a version

    POST   /api/store/migrate              — create tables (Postgres only)
    GET    /api/store/search               — search nodes across ontologies
"""

from __future__ import annotations

import traceback
from typing import Any

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from nexaql.ontology.models import Ontology, OntologyNode
from nexaql.ontology.store import get_store


router = APIRouter(prefix="/store", tags=["store"])


# ── Request models ──────────────────────────────────────────────────────────


class SaveOntologyRequest(BaseModel):
    ontology: dict[str, Any]
    """Full ontology as JSON (will be validated via Ontology model)."""
    author: str = "admin"
    note: str | None = None


class AddNodeRequest(BaseModel):
    name: str
    node: dict[str, Any]
    """Node data (will be validated via OntologyNode model)."""
    author: str = "admin"


class UpdateNodeRequest(BaseModel):
    node: dict[str, Any]
    author: str = "admin"


# ── Domains ─────────────────────────────────────────────────────────────────


@router.get("/domains")
async def list_domains() -> JSONResponse:
    """List all available ontology domains."""
    try:
        store = get_store()
        domains = await store.list_domains()
        return JSONResponse({"domains": domains, "count": len(domains)})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ── Full ontology CRUD ──────────────────────────────────────────────────────


@router.get("/ontology/{domain}")
async def load_ontology(domain: str) -> JSONResponse:
    """Load the active ontology for a domain."""
    try:
        store = get_store()
        ont = await store.load(domain)
        data = ont.model_dump(exclude_none=True)
        return JSONResponse({
            "ontology": data,
            "domain": domain,
            "node_count": len(ont.nodes),
            "nodes": list(ont.nodes.keys()),
        })
    except (FileNotFoundError, KeyError) as e:
        return JSONResponse({"error": str(e)}, status_code=404)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.put("/ontology/{domain}")
async def save_ontology(domain: str, req: SaveOntologyRequest) -> JSONResponse:
    """Save a full ontology (creates a new version)."""
    try:
        # Validate via Pydantic
        ont = Ontology(**req.ontology)
        # Ensure domain matches URL
        ont.domain = domain

        store = get_store()
        meta = await store.save(ont, author=req.author)
        return JSONResponse({"status": "saved", **meta})
    except Exception as e:
        return JSONResponse({"error": str(e), "details": traceback.format_exc().split("\n")[-3:]}, status_code=400)


@router.delete("/ontology/{domain}")
async def delete_domain(domain: str) -> JSONResponse:
    """Delete all versions of a domain."""
    try:
        store = get_store()
        deleted = await store.delete_domain(domain)
        if deleted:
            return JSONResponse({"status": "deleted", "domain": domain})
        return JSONResponse({"error": f"Domain '{domain}' not found"}, status_code=404)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ── Node-level operations ──────────────────────────────────────────────────


@router.post("/ontology/{domain}/node")
async def add_node(domain: str, req: AddNodeRequest) -> JSONResponse:
    """Add a new node to the ontology."""
    try:
        node = OntologyNode(**req.node)
        store = get_store()
        ont = await store.add_node(domain, req.name, node, author=req.author)
        return JSONResponse({
            "status": "added",
            "domain": domain,
            "node": req.name,
            "node_count": len(ont.nodes),
        })
    except KeyError as e:
        return JSONResponse({"error": str(e)}, status_code=409)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@router.put("/ontology/{domain}/node/{node_name}")
async def update_node(domain: str, node_name: str, req: UpdateNodeRequest) -> JSONResponse:
    """Update a single node within the ontology."""
    try:
        node = OntologyNode(**req.node)
        store = get_store()
        ont = await store.update_node(domain, node_name, node, author=req.author)
        return JSONResponse({
            "status": "updated",
            "domain": domain,
            "node": node_name,
            "node_count": len(ont.nodes),
        })
    except (FileNotFoundError, KeyError) as e:
        return JSONResponse({"error": str(e)}, status_code=404)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@router.delete("/ontology/{domain}/node/{node_name}")
async def delete_node(domain: str, node_name: str) -> JSONResponse:
    """Delete a node from the ontology."""
    try:
        store = get_store()
        ont = await store.delete_node(domain, node_name)
        return JSONResponse({
            "status": "deleted",
            "domain": domain,
            "node": node_name,
            "node_count": len(ont.nodes),
        })
    except (FileNotFoundError, KeyError) as e:
        return JSONResponse({"error": str(e)}, status_code=404)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ── Version history ─────────────────────────────────────────────────────────


@router.get("/ontology/{domain}/versions")
async def list_versions(domain: str, limit: int = Query(20, le=100)) -> JSONResponse:
    """List version history for a domain."""
    try:
        store = get_store()
        versions = await store.list_versions(domain, limit)
        return JSONResponse({"domain": domain, "versions": versions, "count": len(versions)})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/ontology/{domain}/version/{version_id}")
async def load_version(domain: str, version_id: int) -> JSONResponse:
    """Load a specific historical version."""
    try:
        store = get_store()
        ont = await store.load_version(domain, version_id)
        return JSONResponse({
            "ontology": ont.model_dump(exclude_none=True),
            "domain": domain,
            "version_id": version_id,
        })
    except (FileNotFoundError, KeyError) as e:
        return JSONResponse({"error": str(e)}, status_code=404)


@router.post("/ontology/{domain}/rollback/{version_id}")
async def rollback_version(domain: str, version_id: int) -> JSONResponse:
    """Rollback to a previous version (creates a new version from the old data)."""
    try:
        store = get_store()
        if not hasattr(store, "rollback"):
            return JSONResponse({"error": "Rollback not supported by YAML store"}, status_code=400)
        meta = await store.rollback(domain, version_id)
        return JSONResponse({"status": "rolled_back", **meta})
    except (FileNotFoundError, KeyError) as e:
        return JSONResponse({"error": str(e)}, status_code=404)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ── Admin ───────────────────────────────────────────────────────────────────


@router.post("/migrate")
async def migrate() -> JSONResponse:
    """Create the ontologies table (Postgres store only)."""
    try:
        store = get_store()
        if not hasattr(store, "migrate"):
            return JSONResponse({"status": "skipped", "reason": "YAML store does not require migration"})
        await store.migrate()
        return JSONResponse({"status": "migrated", "table": "nexaql_ontologies"})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/search")
async def search_nodes(q: str = Query(..., min_length=1)) -> JSONResponse:
    """Search nodes across all active ontologies."""
    try:
        store = get_store()
        if not hasattr(store, "search_nodes"):
            return JSONResponse({"error": "Search not supported by YAML store"}, status_code=400)
        results = await store.search_nodes(q)
        return JSONResponse({"query": q, "results": results, "count": len(results)})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
