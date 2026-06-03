# Copyright (c) 2026-present NexaQL Contributors
"""FastAPI dependencies for NexaQL API routes."""

from __future__ import annotations

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


# ── Cached ontology loader ──────────────────────────────────────────────────


def get_ontology() -> Ontology:
    """Load the ontology specified in the config.

    Uses the file-mtime cache built into :func:`nexaql.ontology.load_ontology`
    so the ontology is automatically reloaded when the YAML file changes.
    """
    cfg = get_config()
    return load_ontology(cfg.ontology.path)


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
