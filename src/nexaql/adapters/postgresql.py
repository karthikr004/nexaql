# Copyright (c) 2026-present NexaQL Contributors
"""PostgreSQL adapter — executes NexaQL queries against a PostgreSQL database."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

import asyncpg

from nexaql.adapters.base import AdapterResult, QueryAdapter
from nexaql.engine.translator import translate
from nexaql.engine.types import ColumnMeta, QueryAST

# asyncpg OID -> friendly type name (covers the most common types)
_PG_TYPE_MAP: Dict[int, str] = {
    16: "boolean",
    20: "integer",
    21: "integer",
    23: "integer",
    25: "string",
    700: "numeric",
    701: "numeric",
    1042: "string",
    1043: "string",
    1082: "date",
    1114: "date",
    1184: "date",
    1700: "numeric",
}


def _pg_oid_to_type(oid: int) -> str:
    return _PG_TYPE_MAP.get(oid, "string")


class PostgreSQLAdapter(QueryAdapter):
    """Async adapter backed by an ``asyncpg`` connection pool."""

    def __init__(self, connection_url: str) -> None:
        self._url = connection_url
        self._pool: Optional[asyncpg.Pool] = None
        self._lock = asyncio.Lock()

    # -- pool management -------------------------------------------------------

    async def _get_pool(self) -> asyncpg.Pool:
        if self._pool is None or self._pool._closed:
            async with self._lock:
                if self._pool is None or self._pool._closed:
                    self._pool = await asyncpg.create_pool(self._url, min_size=1, max_size=5)
        return self._pool

    async def close(self) -> None:
        if self._pool is not None and not self._pool._closed:
            await self._pool.close()
            self._pool = None

    # -- QueryAdapter interface ------------------------------------------------

    @property
    def adapter_type(self) -> str:
        return "postgresql"

    def describe(self, ast: QueryAST, ontology: Any) -> str:
        result = translate(ast, ontology)
        return result.sql

    async def execute(self, ast: QueryAST, ontology: Any) -> AdapterResult:
        result = translate(ast, ontology)
        sql = result.sql

        pool = await self._get_pool()
        async with pool.acquire() as conn:
            stmt = await conn.prepare(sql)
            records = await stmt.fetch()

            # Infer column metadata from the prepared statement attributes
            columns: List[ColumnMeta] = []
            for attr in stmt.get_attributes():
                columns.append(
                    ColumnMeta(
                        name=attr.name,
                        type=_pg_oid_to_type(attr.type.oid),
                    )
                )

            rows: List[Dict[str, Any]] = [dict(r) for r in records]

        return AdapterResult(
            rows=rows,
            columns=columns,
            row_count=len(rows),
            shape=result.shape,
            query_preview=sql,
            adapter_type=self.adapter_type,
        )

    async def healthcheck(self) -> bool:
        try:
            pool = await self._get_pool()
            async with pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            return True
        except Exception:
            return False
