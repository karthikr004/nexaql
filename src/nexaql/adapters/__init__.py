# Copyright (c) 2026-present NexaQL Contributors
"""Adapter registry — maps datasource configs to concrete QueryAdapter instances."""

from __future__ import annotations

from typing import Any, Dict, Type

from nexaql.adapters.base import AdapterResult, QueryAdapter

# Lazy imports to avoid pulling in heavy optional dependencies (asyncpg, duckdb)
# at module-load time.

_ADAPTER_REGISTRY: Dict[str, str] = {
    "postgresql": "nexaql.adapters.postgresql.PostgreSQLAdapter",
    "duckdb": "nexaql.adapters.duckdb_adapter.DuckDBAdapter",
    "csv": "nexaql.adapters.duckdb_adapter.DuckDBAdapter",
}


def _import_class(dotted_path: str) -> Type[QueryAdapter]:
    """Import a class from a fully qualified dotted path."""
    module_path, class_name = dotted_path.rsplit(".", 1)
    import importlib

    module = importlib.import_module(module_path)
    return getattr(module, class_name)


def get_adapter(datasource_config: Any) -> QueryAdapter:
    """Instantiate the appropriate :class:`QueryAdapter` for *datasource_config*.

    Parameters
    ----------
    datasource_config:
        A datasource configuration object (e.g. from ``nexaql.yaml`` or the
        ontology models).  Must expose a ``type`` attribute (``str``) and may
        carry adapter-specific fields such as ``url`` or ``path``.

    Returns
    -------
    QueryAdapter
        A ready-to-use adapter instance.

    Raises
    ------
    ValueError
        If the datasource type is not supported.
    """
    ds_type: str = getattr(datasource_config, "type", None) or (
        datasource_config.get("type") if isinstance(datasource_config, dict) else None
    )

    if ds_type is None:
        raise ValueError("Datasource config must have a 'type' field")

    dotted_path = _ADAPTER_REGISTRY.get(ds_type)
    if dotted_path is None:
        raise ValueError(
            f"Unsupported datasource type '{ds_type}'. "
            f"Supported types: {', '.join(sorted(_ADAPTER_REGISTRY))}"
        )

    adapter_cls = _import_class(dotted_path)

    # Build constructor kwargs from the config
    if ds_type == "postgresql":
        url = getattr(datasource_config, "url", None) or (
            datasource_config.get("url") if isinstance(datasource_config, dict) else None
        )
        if not url:
            raise ValueError("PostgreSQL datasource requires a 'url' field")
        return adapter_cls(connection_url=url)

    if ds_type in ("duckdb", "csv"):
        path = getattr(datasource_config, "path", None) or (
            datasource_config.get("path") if isinstance(datasource_config, dict) else None
        )
        seed_file = getattr(datasource_config, "seed_file", None) or (
            datasource_config.get("seed_file") if isinstance(datasource_config, dict) else None
        )
        return adapter_cls(path=path or ":memory:", seed_file=seed_file)

    # Generic fallback (should not be reached given the registry check above)
    return adapter_cls()


__all__ = [
    "AdapterResult",
    "QueryAdapter",
    "get_adapter",
]
