# Copyright (c) 2026-present NexaQL Contributors
"""FastAPI dependencies for NexaQL API routes."""

from __future__ import annotations

import asyncio
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
    """Load and cache the ``nexaql.yaml`` configuration.

    The config path is resolved from the ``NEXAQL_CONFIG`` environment
    variable, falling back to ``nexaql.yaml`` in the current directory.
    """
    path = os.environ.get("NEXAQL_CONFIG", "nexaql.yaml")
    return load_config(path)


def reload_config() -> NexaQLConfig:
    """Clear the config cache and reload from disk.

    Call this after the config file has been updated (e.g., by the
    datasource wizard writing a new datasource entry).
    """
    get_config.cache_clear()
    return get_config()


# ── Connector DB URL helper ─────────────────────────────────────────────────


def _get_db_url_from_connectors() -> str | None:
    """Get the DB URL from saved connectors (connectors.json).

    Returns the first connector's URL, or None if no connectors exist.
    """
    try:
        from nexaql.api.routes.connectors import get_active_db_url
        return get_active_db_url()
    except Exception:
        return None


# ── Cached ontology loader ──────────────────────────────────────────────────

# In-memory cache for store-loaded ontologies
_store_ontology_cache: dict[str, Ontology] = {}


def _get_active_domain() -> str:
    """Get the active domain name from config or default."""
    try:
        cfg = get_config()
        # Check for domain in ontology config (new style)
        ont_cfg = cfg.ontology
        if hasattr(ont_cfg, 'domain') and ont_cfg.domain:
            return ont_cfg.domain
        # Fall back to extracting from path (legacy)
        if hasattr(ont_cfg, 'path') and ont_cfg.path:
            return os.path.splitext(os.path.basename(ont_cfg.path))[0]
    except Exception:
        pass
    return "default"


def get_ontology(domain: str | None = None) -> Ontology:
    """Load the ontology — from DB (via saved connector) or YAML file fallback.

    Resolution order:
    1. If a saved connector exists (connectors.json), load from the DB's
       nexaql_ontologies table.
    2. Otherwise, fall back to YAML path in config (legacy behavior).
    """
    if domain is None:
        domain = _get_active_domain()

    # Try loading from DB via saved connector
    db_url = _get_db_url_from_connectors()
    if db_url:
        # Check cache
        if domain in _store_ontology_cache:
            return _store_ontology_cache[domain]

        from nexaql.ontology.store import PostgresStore
        store = PostgresStore(db_url)

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

    # Fallback: YAML file (legacy, no connectors configured)
    cfg = get_config()
    return load_ontology(cfg.ontology.path)


async def get_ontology_async(domain: str | None = None) -> Ontology:
    """Async version of get_ontology — preferred in async FastAPI routes."""
    if domain is None:
        domain = _get_active_domain()

    # Try loading from DB via saved connector
    db_url = _get_db_url_from_connectors()
    if db_url:
        if domain in _store_ontology_cache:
            return _store_ontology_cache[domain]

        from nexaql.ontology.store import PostgresStore
        store = PostgresStore(db_url)
        ont = await store.load(domain)
        _store_ontology_cache[domain] = ont
        return ont

    # Fallback: YAML (sync, but fast with mtime cache)
    cfg = get_config()
    return load_ontology(cfg.ontology.path)


def invalidate_ontology_cache(domain: str | None = None) -> None:
    """Clear the ontology cache (both YAML and store).

    Call this after modifying the ontology to ensure fresh data.
    """
    if domain:
        _store_ontology_cache.pop(domain, None)
    else:
        _store_ontology_cache.clear()

    from nexaql.ontology import invalidate_cache
    invalidate_cache()


# ── Adapter factory ─────────────────────────────────────────────────────────


_adapter_cache: dict[str, QueryAdapter] = {}


def get_adapter_for_datasource(datasource_name: str | None = None) -> QueryAdapter:
    """Get or create a :class:`QueryAdapter` from the config's datasource entry.

    Adapters are cached so in-memory DuckDB databases retain seeded data.
    If *datasource_name* is ``None`` the first datasource in the config is used.
    """
    cfg = get_config()

    if not cfg.datasources:
        raise ValueError("No datasources configured in nexaql.yaml")

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
