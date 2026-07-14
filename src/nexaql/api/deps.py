# Copyright (c) 2026-present NexaQL Contributors
"""FastAPI dependencies for NexaQL API routes.

Uses the bootstrap database (~/.nexaql/nexaql.db) as the primary config source.
Falls back to nexaql.yaml for legacy setups.
"""

from __future__ import annotations

import asyncio
import json
import os
from functools import lru_cache
from typing import Any

from nexaql.adapters import get_adapter as _get_adapter
from nexaql.adapters.base import QueryAdapter
from nexaql.config import NexaQLConfig, load_config
from nexaql.ontology import Ontology, load_ontology


# ── Cached config loader ────────────────────────────────────────────────────


@lru_cache(maxsize=1)
def get_config() -> NexaQLConfig:
    """Load and cache configuration.

    Resolution order:
    1. Bootstrap DB (~/.nexaql/nexaql.db)
    2. nexaql.yaml (legacy fallback)
    """
    path = os.environ.get("NEXAQL_CONFIG", "nexaql.yaml")
    return load_config(path)


def reload_config() -> NexaQLConfig:
    """Clear the config cache and reload.

    Call this after the bootstrap DB or config file has been updated.
    """
    get_config.cache_clear()
    return get_config()


# ── Connector DB URL helper ─────────────────────────────────────────────────


def _get_db_url_from_connectors() -> str | None:
    """Get the DB URL from the bootstrap database connectors.

    Checks the active domain's schemas first (to get the right connector),
    then falls back to the first connector.
    """
    try:
        from nexaql import bootstrap as bs

        # Try active domain's connector first
        active_domain = bs.get_active_domain()
        if active_domain:
            schemas = bs.list_schemas(active_domain)
            if schemas:
                connector = bs.get_connector_by_id(schemas[0]["connector_id"])
                if connector and connector.get("url"):
                    return connector["url"]

        # Fall back to first connector
        connectors = bs.list_connectors()
        if connectors:
            return connectors[0].get("url")
    except Exception:
        pass

    # Legacy fallback: connectors.json
    try:
        from nexaql.api.routes.connectors import get_active_db_url
        return get_active_db_url()
    except Exception:
        return None


# ── Cached ontology loader ──────────────────────────────────────────────────

# In-memory cache for store-loaded ontologies
_store_ontology_cache: dict[str, Ontology] = {}


def _get_active_domain() -> str:
    """Get the active domain name from bootstrap DB or config."""
    try:
        from nexaql import bootstrap as bs
        domain = bs.get_active_domain()
        if domain:
            return domain
    except Exception:
        pass

    try:
        cfg = get_config()
        ont_cfg = cfg.ontology
        if hasattr(ont_cfg, 'domain') and ont_cfg.domain:
            return ont_cfg.domain
        if hasattr(ont_cfg, 'path') and ont_cfg.path:
            return os.path.splitext(os.path.basename(ont_cfg.path))[0]
    except Exception:
        pass
    return "default"


def _get_store_for_datasource():
    """Get the right ontology store based on datasource type.

    Resolution order:
    1. Bootstrap DB connector for the active domain
    2. Saved connector (connectors.json legacy)
    3. Config datasource
    4. Fallback: DuckDB with default file
    """
    from nexaql.ontology.store import DuckDBStore, PostgresStore

    # 1. Bootstrap DB connector
    db_url = _get_db_url_from_connectors()
    if db_url:
        if db_url.startswith("postgresql"):
            return PostgresStore(db_url)
        else:
            return DuckDBStore(db_url)

    # 2. Config datasource
    try:
        cfg = get_config()
        if cfg.datasources:
            ds = next(iter(cfg.datasources.values()))
            if ds.type == "postgresql" and ds.url:
                return PostgresStore(ds.url)
            elif ds.type == "duckdb" and ds.path:
                return DuckDBStore(ds.path)
    except Exception:
        pass

    # 3. Fallback: local DuckDB
    return DuckDBStore("nexaql.duckdb")


def _try_bootstrap_ontology(domain: str) -> Ontology | None:
    """Try to load ontology from the bootstrap database (schema-per-ontology model)."""
    try:
        from nexaql import bootstrap as bs

        ont_data = bs.get_domain_ontology(domain)
        if ont_data and ont_data.get("nodes"):
            # Convert bootstrap ontology format to Ontology model
            # Build a dict compatible with Ontology(**data)
            return load_ontology_from_dict(ont_data)
    except Exception:
        pass
    return None


def load_ontology_from_dict(data: dict) -> Ontology:
    """Load an Ontology object from a bootstrap ontology dict."""
    from nexaql.ontology import Ontology

    # The bootstrap format has: domain, description, nodes, node_to_connector,
    # and optionally roles and access_functions from the original YAML.
    ont_dict: dict = {
        "domain": data.get("domain", ""),
        "description": data.get("description", ""),
        "version": data.get("version", "1.0"),
        "nodes": data.get("nodes", {}),
    }
    if data.get("roles"):
        ont_dict["roles"] = data["roles"]
    if data.get("access_functions"):
        ont_dict["access_functions"] = data["access_functions"]
    if data.get("node_to_connector"):
        ont_dict["node_to_connector"] = data["node_to_connector"]
    return Ontology(**ont_dict)


def get_ontology(domain: str | None = None) -> Ontology:
    """Load the ontology for a domain.

    Resolution order:
    1. In-memory cache
    2. Bootstrap DB (schema-per-ontology model)
    3. Database store (nexaql_ontologies table)
    4. YAML file (legacy fallback)
    """
    if domain is None:
        domain = _get_active_domain()

    # Check cache
    if domain in _store_ontology_cache:
        return _store_ontology_cache[domain]

    # 1. Try bootstrap DB (new schema-per-ontology model)
    ont = _try_bootstrap_ontology(domain)
    if ont:
        _store_ontology_cache[domain] = ont
        return ont

    # 2. Try database store (nexaql_ontologies table — existing model)
    store = _get_store_for_datasource()

    try:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                ont = executor.submit(
                    lambda: asyncio.run(store.load(domain))
                ).result()
        else:
            ont = asyncio.run(store.load(domain))

        _store_ontology_cache[domain] = ont
        return ont
    except (KeyError, FileNotFoundError):
        pass

    # 3. Legacy fallback: YAML file
    try:
        cfg = get_config()
        if cfg.ontology.path:
            return load_ontology(cfg.ontology.path)
    except Exception:
        pass

    raise RuntimeError(
        f"No ontology found for domain '{domain}'. "
        "Add a connector and generate an ontology from the Admin panel."
    )


async def get_ontology_async(domain: str | None = None) -> Ontology:
    """Async version of get_ontology."""
    if domain is None:
        domain = _get_active_domain()

    if domain in _store_ontology_cache:
        return _store_ontology_cache[domain]

    # 1. Try bootstrap DB
    ont = _try_bootstrap_ontology(domain)
    if ont:
        _store_ontology_cache[domain] = ont
        return ont

    # 2. Try database store
    store = _get_store_for_datasource()

    try:
        ont = await store.load(domain)
        _store_ontology_cache[domain] = ont
        return ont
    except (KeyError, FileNotFoundError):
        pass

    # 3. Legacy fallback
    try:
        cfg = get_config()
        if cfg.ontology.path:
            return load_ontology(cfg.ontology.path)
    except Exception:
        pass

    raise RuntimeError(
        f"No ontology found for domain '{domain}'. "
        "Add a connector and generate an ontology from the Admin panel."
    )


def invalidate_ontology_cache(domain: str | None = None) -> None:
    """Clear the ontology cache."""
    if domain:
        _store_ontology_cache.pop(domain, None)
    else:
        _store_ontology_cache.clear()

    from nexaql.ontology import invalidate_cache
    invalidate_cache()


# ── Adapter factory ─────────────────────────────────────────────────────────


_adapter_cache: dict[str, QueryAdapter] = {}


def get_adapter_for_connector(connector_id: int) -> QueryAdapter:
    """Get or create a QueryAdapter for a bootstrap DB connector by ID."""
    cache_key = f"__connector_{connector_id}"
    if cache_key in _adapter_cache:
        return _adapter_cache[cache_key]

    from nexaql import bootstrap as bs
    from nexaql.config import DatasourceEntry

    connector = bs.get_connector_by_id(connector_id)
    if connector is None:
        raise ValueError(f"Connector with id={connector_id} not found")

    ds_entry = DatasourceEntry(
        type=connector["type"],
        url=connector.get("url"),
        path=connector.get("url"),
    )

    adapter = _get_adapter(ds_entry)
    _adapter_cache[cache_key] = adapter
    return adapter


def get_adapter_for_datasource(datasource_name: str | None = None) -> QueryAdapter:
    """Get or create a QueryAdapter.

    Resolves from bootstrap DB connectors first, then config datasources.
    """
    cfg = get_config()

    if not cfg.datasources:
        raise ValueError(
            "No datasources configured. Add a connector in the Admin panel."
        )

    if datasource_name is None:
        datasource_name = next(iter(cfg.datasources))

    if datasource_name in _adapter_cache:
        return _adapter_cache[datasource_name]

    ds_entry = cfg.datasources.get(datasource_name)
    if ds_entry is None:
        available = ", ".join(cfg.datasources.keys())
        raise ValueError(
            f"Datasource '{datasource_name}' not found. Available: {available}"
        )

    adapter = _get_adapter(ds_entry)
    _adapter_cache[datasource_name] = adapter
    return adapter
