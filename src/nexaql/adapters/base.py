# Copyright (c) 2026-present NexaQL Contributors
"""Abstract base class and shared types for database adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from nexaql.engine.types import ColumnMeta, NodeShape, QueryAST


@dataclass
class AdapterResult:
    """Result returned by a QueryAdapter after executing a query."""

    rows: List[Dict[str, Any]]
    columns: List[ColumnMeta]
    row_count: int
    shape: NodeShape
    query_preview: str
    adapter_type: str


class QueryAdapter(ABC):
    """Interface that every database adapter must implement."""

    @property
    @abstractmethod
    def adapter_type(self) -> str:
        """Short identifier for this adapter (e.g. ``'postgresql'``, ``'duckdb'``)."""
        ...

    @abstractmethod
    async def execute(self, ast: QueryAST, ontology: Any) -> AdapterResult:
        """Translate *ast* to SQL using *ontology*, run it, and return the result."""
        ...

    @abstractmethod
    def describe(self, ast: QueryAST, ontology: Any) -> str:
        """Translate *ast* to SQL and return the SQL string without executing."""
        ...

    @abstractmethod
    async def healthcheck(self) -> bool:
        """Return ``True`` if the underlying datasource is reachable."""
        ...
