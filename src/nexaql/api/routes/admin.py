# Copyright (c) 2026-present NexaQL Contributors
"""Admin endpoints for managing the NexaQL ontology."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from nexaql.api.deps import get_config, get_ontology
from nexaql.ontology.models import Ontology, OntologyNode
from nexaql.ontology.writer import save_ontology

router = APIRouter(tags=["admin"])


def _ontology_path() -> str:
    return get_config().ontology.path


# ── GET /admin/ontology ────────────────────────────────────────────────────


@router.get("/admin/ontology")
async def get_full_ontology() -> JSONResponse:
    try:
        ont = get_ontology()
        return JSONResponse({
            "ontology": ont.model_dump(exclude_none=True),
            "path": _ontology_path(),
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ── PUT /admin/ontology ────────────────────────────────────────────────────


@router.put("/admin/ontology")
async def replace_ontology(data: dict[str, Any]) -> JSONResponse:
    try:
        ontology = Ontology(**data)
    except ValidationError as e:
        return JSONResponse({"error": str(e)}, status_code=400)

    try:
        save_ontology(ontology, _ontology_path())
        return JSONResponse({"success": True})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ── PUT /admin/ontology/node/{node_name} ───────────────────────────────────


@router.put("/admin/ontology/node/{node_name}")
async def update_node(node_name: str, data: dict[str, Any]) -> JSONResponse:
    try:
        node = OntologyNode(**data)
    except ValidationError as e:
        return JSONResponse({"error": str(e)}, status_code=400)

    try:
        ont = get_ontology()
        if node_name not in ont.nodes:
            return JSONResponse(
                {"error": f"Node '{node_name}' not found"},
                status_code=404,
            )
        ont.nodes[node_name] = node
        # Re-validate full ontology after mutation
        ontology = Ontology(**ont.model_dump())
        save_ontology(ontology, _ontology_path())
        return JSONResponse({"success": True, "node": node_name})
    except ValidationError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ── POST /admin/ontology/node ─────────────────────────────────────────────


@router.post("/admin/ontology/node")
async def create_node(data: dict[str, Any]) -> JSONResponse:
    name = data.get("name")
    node_data = data.get("node")

    if not name or not node_data:
        return JSONResponse(
            {"error": "Request body must include 'name' (str) and 'node' (dict)"},
            status_code=400,
        )

    try:
        node = OntologyNode(**node_data)
    except ValidationError as e:
        return JSONResponse({"error": str(e)}, status_code=400)

    try:
        ont = get_ontology()
        if name in ont.nodes:
            return JSONResponse(
                {"error": f"Node '{name}' already exists"},
                status_code=400,
            )
        ont.nodes[name] = node
        # Re-validate full ontology after mutation
        ontology = Ontology(**ont.model_dump())
        save_ontology(ontology, _ontology_path())
        return JSONResponse({"success": True, "node": name})
    except ValidationError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ── DELETE /admin/ontology/node/{node_name} ────────────────────────────────


@router.delete("/admin/ontology/node/{node_name}")
async def delete_node(node_name: str) -> JSONResponse:
    try:
        ont = get_ontology()
        if node_name not in ont.nodes:
            return JSONResponse(
                {"error": f"Node '{node_name}' not found"},
                status_code=404,
            )
        del ont.nodes[node_name]
        save_ontology(ont, _ontology_path())
        return JSONResponse({"success": True})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
