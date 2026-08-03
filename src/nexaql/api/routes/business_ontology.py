# Copyright (c) 2026-present NexaQL Contributors
"""Business ontology CRUD API — domain-specific terms, definitions, SQL hints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from nexaql import bootstrap as bs

router = APIRouter()


class CreateEntryRequest(BaseModel):
    term: str
    definition: str
    sql_hint: str | None = None
    tags: list[str] = []


class UpdateEntryRequest(BaseModel):
    term: str | None = None
    definition: str | None = None
    sql_hint: str | None = ...
    tags: list[str] | None = ...


def _get_domain_or_404(domain_name: str) -> dict:
    domain = bs.get_domain(domain_name)
    if not domain:
        raise HTTPException(status_code=404, detail=f"Domain '{domain_name}' not found")
    return domain


@router.get("/domains/{domain_name}/ontology/business")
async def list_entries(domain_name: str):
    domain = _get_domain_or_404(domain_name)
    return bs.list_business_ontology(domain["id"])


@router.post("/domains/{domain_name}/ontology/business", status_code=201)
async def create_entry(domain_name: str, body: CreateEntryRequest, request: Request):
    domain = _get_domain_or_404(domain_name)
    if not body.term.strip() or not body.definition.strip():
        raise HTTPException(status_code=400, detail="Term and definition are required")
    try:
        entry = bs.create_business_ontology_entry(
            domain_id=domain["id"],
            term=body.term.strip(),
            definition=body.definition.strip(),
            sql_hint=body.sql_hint.strip() if body.sql_hint else None,
            tags=body.tags,
        )
    except Exception as e:
        if "UNIQUE constraint" in str(e):
            raise HTTPException(status_code=409, detail=f"Term '{body.term}' already exists in this domain")
        raise
    return entry


@router.get("/domains/{domain_name}/ontology/business/{entry_id}")
async def get_entry(domain_name: str, entry_id: int):
    _get_domain_or_404(domain_name)
    entry = bs.get_business_ontology_entry(entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    return entry


@router.patch("/domains/{domain_name}/ontology/business/{entry_id}")
async def update_entry(domain_name: str, entry_id: int, body: UpdateEntryRequest):
    _get_domain_or_404(domain_name)
    existing = bs.get_business_ontology_entry(entry_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Entry not found")

    kwargs: dict = {}
    if body.term is not None:
        kwargs["term"] = body.term.strip()
    if body.definition is not None:
        kwargs["definition"] = body.definition.strip()
    if body.sql_hint is not ...:
        kwargs["sql_hint"] = body.sql_hint.strip() if body.sql_hint else None
    if body.tags is not ...:
        kwargs["tags"] = body.tags

    updated = bs.update_business_ontology_entry(entry_id, **kwargs)
    return updated


@router.delete("/domains/{domain_name}/ontology/business/{entry_id}")
async def delete_entry(domain_name: str, entry_id: int):
    _get_domain_or_404(domain_name)
    deleted = bs.delete_business_ontology_entry(entry_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Entry not found")
    return {"ok": True}


@router.get("/domains/{domain_name}/ontology/business/lookup")
async def lookup_entries(domain_name: str, q: str = ""):
    domain = _get_domain_or_404(domain_name)
    if not q.strip():
        return []
    return bs.lookup_business_ontology(domain["id"], q.strip())
