# Copyright (c) 2026-present NexaQL Contributors
"""Ontology API — summary, domain listing, and domain switching.

All domain/schema data comes exclusively from the bootstrap database
(~/.nexaql/nexaql.db). No fallback to connected DBs or YAML files.
"""

from __future__ import annotations

import json as _json
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from nexaql import bootstrap as bs
from nexaql.api.deps import (
    _adapter_cache,
    get_ontology,
    invalidate_ontology_cache,
    reload_config,
)
from nexaql.ontology import ontology_summary

router = APIRouter()


@router.get("/ontology")
async def ontology_endpoint() -> JSONResponse:
    try:
        ont = get_ontology()
        return JSONResponse(ontology_summary(ont))
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ── GET /api/domains — list domains from bootstrap DB only ───────────────────


@router.get("/domains")
async def list_domains() -> JSONResponse:
    """List ontology domains stored in the bootstrap database."""
    active_domain = bs.get_active_domain()
    domains: list[dict[str, Any]] = []

    try:
        for d in bs.list_domains():
            domain_name = d["name"]
            schemas = bs.list_schemas(domain_name)

            # Sum node counts across all schemas in this domain
            total_nodes = 0
            for s in schemas:
                try:
                    ont_data = _json.loads(s.get("ontology_json", "{}"))
                    total_nodes += len(ont_data.get("nodes", {}))
                except Exception:
                    pass

            domains.append({
                "domain": domain_name,
                "description": d.get("description", ""),
                "nodeCount": total_nodes or d.get("schema_count", 0),
                "active": domain_name == active_domain,
                "source": "bootstrap_db",
                "schema_count": len(schemas),
            })
    except Exception:
        pass

    return JSONResponse({
        "domains": domains,
        "activeDomain": active_domain,
    })


# ── GET /api/domains/{domain}/schemas — list schemas in a domain ─────────────


@router.get("/domains/{domain}/schemas")
async def list_domain_schemas(domain: str) -> JSONResponse:
    """List all schemas belonging to a domain (bootstrap DB only)."""
    bs_domain = bs.get_domain(domain)
    if not bs_domain:
        return JSONResponse({"error": f"Domain '{domain}' not found"}, status_code=404)

    result: list[dict[str, Any]] = []
    for s in bs.list_schemas(domain):
        connector_name = None
        try:
            connector = bs.get_connector_by_id(s["connector_id"])
            if connector:
                connector_name = connector.get("name")
        except Exception:
            pass

        node_count = 0
        try:
            ont_data = _json.loads(s.get("ontology_json", "{}"))
            node_count = len(ont_data.get("nodes", {}))
        except Exception:
            pass

        result.append({
            "id": s["id"],
            "name": s["name"],
            "connector_id": s["connector_id"],
            "connector_name": connector_name,
            "node_count": node_count,
            "created_at": s.get("created_at", ""),
            "updated_at": s.get("updated_at", ""),
        })

    return JSONResponse({"schemas": result, "domain": domain, "count": len(result)})


@router.delete("/domains/{domain}/schemas/{schema_name}")
async def delete_domain_schema(domain: str, schema_name: str) -> JSONResponse:
    """Delete a schema from a domain."""
    deleted = bs.delete_schema(domain, schema_name)
    if not deleted:
        return JSONResponse({"error": f"Schema '{schema_name}' not found in domain '{domain}'"}, status_code=404)
    return JSONResponse({"status": "deleted", "domain": domain, "schema": schema_name})


@router.delete("/domains/{domain}")
async def delete_domain(domain: str) -> JSONResponse:
    """Delete a domain and all its schemas."""
    existing = bs.get_domain(domain)
    if not existing:
        return JSONResponse({"error": f"Domain '{domain}' not found"}, status_code=404)
    for s in bs.list_schemas(domain):
        bs.delete_schema(domain, s["name"])
    bs.delete_domain(domain)
    return JSONResponse({"status": "deleted", "domain": domain})


# ── POST /api/domains/switch — switch the active domain ──────────────────────


class SwitchDomainRequest(BaseModel):
    domain: str
    """Domain name to switch to."""


@router.post("/domains/switch")
async def switch_domain(req: SwitchDomainRequest) -> JSONResponse:
    """Switch the active ontology to a different domain.

    Only bootstrap DB domains are valid targets.
    """
    bs_domain = bs.get_domain(req.domain)
    if not bs_domain:
        return JSONResponse({"error": f"Domain '{req.domain}' not found in bootstrap DB"}, status_code=404)

    schemas = bs.list_schemas(req.domain)
    if not schemas:
        return JSONResponse({"error": f"Domain '{req.domain}' has no schemas"}, status_code=404)

    # Update active domain
    bs.set_active_domain(req.domain)

    # Reload caches
    reload_config()
    invalidate_ontology_cache()
    _adapter_cache.clear()

    # Return summary
    try:
        ont = get_ontology(req.domain)
        summary = ontology_summary(ont)
        return JSONResponse({
            "status": "switched",
            "domain": ont.domain,
            "description": ont.description,
            "nodeCount": len(ont.nodes),
            "nodes": [n["name"] for n in summary["nodes"]],
        })
    except Exception:
        return JSONResponse({
            "status": "switched",
            "domain": req.domain,
        })
