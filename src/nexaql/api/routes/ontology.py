# Copyright (c) 2026-present NexaQL Contributors
"""Ontology API — summary, domain listing, and domain switching."""

from __future__ import annotations

import os
from typing import Any

import yaml
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from nexaql.api.deps import (
    _adapter_cache,
    get_config,
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


# ── GET /api/domains — list available ontology domains ────────────────────────


@router.get("/domains")
async def list_domains() -> JSONResponse:
    """List available ontology domains from the database.

    Reads from the nexaql_ontologies table via the saved connector.
    Falls back to scanning YAML files if no connector is configured.
    """
    from nexaql.api.deps import _get_db_url_from_connectors, _get_active_domain

    active_domain = _get_active_domain()
    domains: list[dict[str, Any]] = []

    db_url = _get_db_url_from_connectors()
    if db_url:
        # Load domains from DB
        try:
            from nexaql.ontology.store import PostgresStore
            store = PostgresStore(db_url)
            store_domains = await store.list_domains()

            for sd in store_domains:
                domain_name = sd["domain"]
                # Load the ontology to get description and node count
                try:
                    ont = await store.load(domain_name)
                    description = ont.description
                    node_count = len(ont.nodes)
                except Exception:
                    description = ""
                    node_count = 0

                domains.append({
                    "domain": domain_name,
                    "description": description,
                    "nodeCount": node_count,
                    "active": domain_name == active_domain,
                    "source": "database",
                    "version": sd.get("latest_version"),
                })
        except Exception as e:
            return JSONResponse({"error": f"Failed to list domains: {e}"}, status_code=500)
    else:
        # Fallback: scan YAML files (legacy, no connector configured)
        import glob
        ontology_dir = os.environ.get("NEXAQL_ONTOLOGY_DIR", "ontologies")
        cfg = get_config()
        active_path = getattr(cfg.ontology, 'path', '')

        if os.path.isdir(ontology_dir):
            for fpath in sorted(glob.glob(os.path.join(ontology_dir, "*.yaml"))):
                try:
                    with open(fpath) as f:
                        raw = yaml.safe_load(f)
                    if not raw or "nodes" not in raw:
                        continue
                    domain_name = raw.get("domain", os.path.splitext(os.path.basename(fpath))[0])
                    domains.append({
                        "domain": domain_name,
                        "description": raw.get("description", ""),
                        "nodeCount": len(raw.get("nodes", {})),
                        "path": fpath,
                        "active": os.path.normpath(fpath) == os.path.normpath(active_path),
                        "source": "file",
                    })
                except Exception:
                    continue

    return JSONResponse({
        "domains": domains,
        "activeDomain": active_domain,
    })


# ── POST /api/domains/switch — switch the active domain ──────────────────────


class SwitchDomainRequest(BaseModel):
    domain: str
    """Domain name to switch to."""


@router.post("/domains/switch")
async def switch_domain(req: SwitchDomainRequest) -> JSONResponse:
    """Switch the active ontology to a different domain.

    Updates nexaql.yaml and reloads all caches so subsequent
    queries use the new ontology.
    """
    from nexaql.api.deps import _get_db_url_from_connectors

    db_url = _get_db_url_from_connectors()

    if db_url:
        # Verify domain exists in DB
        try:
            from nexaql.ontology.store import PostgresStore
            store = PostgresStore(db_url)
            ont = await store.load(req.domain)
        except KeyError:
            return JSONResponse({"error": f"Domain '{req.domain}' not found in database"}, status_code=404)
        except Exception as e:
            return JSONResponse({"error": f"Failed to load domain: {e}"}, status_code=500)
    else:
        return JSONResponse({"error": "No connector configured"}, status_code=400)

    # Update nexaql.yaml to set the active domain
    try:
        config_path = os.environ.get("NEXAQL_CONFIG", "nexaql.yaml")
        with open(config_path) as f:
            raw_config = yaml.safe_load(f) or {}

        raw_config["ontology"] = {"domain": req.domain}

        with open(config_path, "w") as f:
            f.write("# NexaQL configuration — updated by Domain Selector\n")
            yaml.dump(raw_config, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
    except Exception as e:
        return JSONResponse({"error": f"Failed to update config: {e}"}, status_code=500)

    # Reload everything
    reload_config()
    invalidate_ontology_cache()
    _adapter_cache.clear()

    summary = ontology_summary(ont)
    return JSONResponse({
        "status": "switched",
        "domain": ont.domain,
        "description": ont.description,
        "nodeCount": len(ont.nodes),
        "nodes": [n["name"] for n in summary["nodes"]],
    })
