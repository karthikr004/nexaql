# Copyright (c) 2026-present NexaQL Contributors
"""Ontology generator — introspect structured databases and auto-generate
NexaQL ontology YAML.

Supports PostgreSQL, MySQL, and DuckDB. Connects to the target database,
reads information_schema, discovers tables/columns/FKs/enums, and produces
a complete Ontology model that can be serialized to YAML.

Usage::

    from nexaql.ontology.generator import OntologyGenerator

    gen = OntologyGenerator(connection_url="postgresql://user:pass@localhost/mydb")
    ontology = await gen.generate(
        schema="public",
        domain="my_app",
        description="Auto-generated from my_app database",
    )
    gen.save(ontology, "ontologies/my_app.yaml")

CLI::

    nexaql generate --from postgresql://user:pass@localhost/mydb \\
                    --schema public \\
                    --output ontologies/my_app.yaml
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

from nexaql.ontology.models import (
    DatasourceConfig,
    DuckDBDatasource,
    FieldDef,
    JoinStep,
    MySQLDatasource,
    Ontology,
    OntologyEdge,
    OntologyNode,
    PostgreSQLDatasource,
)


# ── Introspected schema types ────────────────────────────────────────────────


@dataclass
class ColumnInfo:
    """Introspected column metadata."""

    name: str
    data_type: str
    is_nullable: bool
    column_default: Optional[str] = None
    character_maximum_length: Optional[int] = None
    is_primary_key: bool = False
    is_foreign_key: bool = False
    foreign_table: Optional[str] = None
    foreign_column: Optional[str] = None
    ordinal_position: int = 0


@dataclass
class TableInfo:
    """Introspected table metadata."""

    name: str
    schema_name: str
    columns: list[ColumnInfo] = field(default_factory=list)
    primary_key: Optional[str] = None
    row_count_estimate: Optional[int] = None
    comment: Optional[str] = None


@dataclass
class ForeignKey:
    """Introspected foreign key relationship."""

    from_table: str
    from_column: str
    to_table: str
    to_column: str
    constraint_name: str


# ── Type mapping ─────────────────────────────────────────────────────────────

# Map DB column types → NexaQL field types
_TYPE_MAP: dict[str, str] = {
    # Integer types
    "integer": "integer",
    "int": "integer",
    "int4": "integer",
    "int8": "integer",
    "bigint": "integer",
    "smallint": "integer",
    "tinyint": "integer",
    "serial": "integer",
    "bigserial": "integer",
    # Numeric types
    "numeric": "numeric",
    "decimal": "numeric",
    "real": "numeric",
    "double precision": "numeric",
    "float": "numeric",
    "float4": "numeric",
    "float8": "numeric",
    "money": "numeric",
    # String types
    "character varying": "string",
    "varchar": "string",
    "text": "string",
    "char": "string",
    "character": "string",
    "name": "string",
    "uuid": "string",
    "citext": "string",
    "bpchar": "string",
    # Boolean
    "boolean": "boolean",
    "bool": "boolean",
    # Date/time types
    "date": "date",
    "timestamp": "date",
    "timestamp without time zone": "date",
    "timestamp with time zone": "date",
    "timestamptz": "date",
    "time": "date",
    "time without time zone": "date",
    "interval": "string",
    # JSON (treat as string for now)
    "json": "string",
    "jsonb": "string",
    # Array (treat as string)
    "array": "string",
    "user-defined": "string",
}

# Patterns that suggest a column is PII
_PII_PATTERNS = [
    r"ssn", r"social_security", r"tax_id", r"national_id",
    r"passport", r"driver_license", r"credit_card", r"card_number",
    r"bank_account", r"routing_number", r"iban",
    r"date_of_birth", r"dob", r"birth_date",
    r"phone", r"mobile", r"cell",
    r"email", r"e_mail",
    r"address", r"street", r"zip_code", r"postal_code",
    r"salary", r"compensation", r"wage",
    r"password", r"secret", r"token",
]

# Patterns for common enum columns (low cardinality)
_ENUM_PATTERNS = [
    r"status", r"state", r"type", r"category", r"priority",
    r"severity", r"level", r"tier", r"grade", r"rating",
    r"country_code", r"currency_code", r"language",
    r"gender", r"role", r"department",
]

# Columns to exclude from the ontology (system columns)
_SYSTEM_COLUMNS = {
    "created_at", "updated_at", "deleted_at", "created_by", "updated_by",
    "version", "row_version", "last_modified",
}


def _map_type(db_type: str) -> str:
    """Map a database column type to a NexaQL field type."""
    normalized = db_type.lower().strip()
    # Handle parameterized types: varchar(255) → varchar
    base = re.split(r"[\(\[]", normalized)[0].strip()
    return _TYPE_MAP.get(base, "string")


def _is_pii(column_name: str) -> bool:
    """Heuristic check if a column likely contains PII."""
    name = column_name.lower()
    return any(re.search(pattern, name) for pattern in _PII_PATTERNS)


def _is_likely_enum(column_name: str) -> bool:
    """Heuristic check if a column is likely an enum."""
    name = column_name.lower()
    return any(re.search(pattern, name) for pattern in _ENUM_PATTERNS)


def _table_to_node_name(table_name: str) -> str:
    """Convert a table name to a NexaQL node name.

    Conventions:
    - Lowercase, underscored (already typical)
    - Strip common prefixes (tbl_, t_)
    - Keep as-is if already clean
    """
    name = table_name.lower()
    for prefix in ("tbl_", "t_", "tb_"):
        if name.startswith(prefix):
            name = name[len(prefix):]
    return name


def _column_to_description(column_name: str, table_name: str) -> str:
    """Generate a human-readable description from a column name."""
    # Replace underscores with spaces, title case
    words = column_name.replace("_", " ").replace("id", "ID").title()
    return words


def _infer_edge_name(fk: ForeignKey) -> str:
    """Infer a human-friendly edge name from a foreign key.

    E.g., customer_id → customer, fk_order_product → product
    """
    col = fk.from_column.lower()
    # Strip _id suffix
    if col.endswith("_id"):
        return col[:-3]
    # Use the target table name
    return _table_to_node_name(fk.to_table)


# ── Generator ────────────────────────────────────────────────────────────────


class OntologyGenerator:
    """Generates NexaQL ontology from a database schema.

    Connects to the target database, introspects tables/columns/FKs,
    and produces a complete Ontology model.
    """

    def __init__(self, connection_url: str) -> None:
        self._url = connection_url
        self._db_type = self._detect_db_type(connection_url)

    @staticmethod
    def _detect_db_type(url: str) -> str:
        if url.startswith("postgresql://") or url.startswith("postgres://"):
            return "postgresql"
        elif url.startswith("mysql://") or url.startswith("mysql+"):
            return "mysql"
        elif url.endswith(".duckdb") or url.endswith(".db") or url == ":memory:":
            return "duckdb"
        else:
            raise ValueError(f"Unsupported database URL: {url}")

    # ── Introspection ────────────────────────────────────────────────

    async def introspect(self, schema: str = "public",
                         exclude_tables: list[str] | None = None,
                         include_tables: list[str] | None = None) -> tuple[list[TableInfo], list[ForeignKey]]:
        """Introspect the database schema.

        Returns (tables, foreign_keys).
        """
        if self._db_type == "postgresql":
            return await self._introspect_postgresql(schema, exclude_tables, include_tables)
        elif self._db_type == "duckdb":
            return await self._introspect_duckdb(schema, exclude_tables, include_tables)
        elif self._db_type == "mysql":
            return await self._introspect_mysql(schema, exclude_tables, include_tables)
        else:
            raise ValueError(f"Unsupported DB type: {self._db_type}")

    async def _introspect_postgresql(
        self, schema: str,
        exclude_tables: list[str] | None,
        include_tables: list[str] | None,
    ) -> tuple[list[TableInfo], list[ForeignKey]]:
        import asyncpg

        conn = await asyncpg.connect(self._url)
        try:
            # Get tables
            table_filter = ""
            params: list[Any] = [schema]
            if include_tables:
                table_filter = f" AND t.table_name = ANY($2)"
                params.append(include_tables)
            elif exclude_tables:
                table_filter = f" AND t.table_name != ALL($2)"
                params.append(exclude_tables)

            # Use pg_catalog instead of information_schema to avoid permission issues
            # (information_schema only shows tables the current user has privileges on)
            tables_sql = f"""
                SELECT c.relname AS table_name, obj_description(c.oid) AS comment
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = $1
                AND c.relkind = 'r'
                AND c.relname NOT LIKE 'pg_%%'
                {table_filter.replace('t.table_name', 'c.relname')}
                ORDER BY c.relname
            """
            table_rows = await conn.fetch(tables_sql, *params)

            tables: list[TableInfo] = []
            for tr in table_rows:
                tname = tr["table_name"]

                # Get columns using pg_catalog (avoids permission issues)
                col_sql = """
                    SELECT a.attname AS column_name,
                           pg_catalog.format_type(a.atttypid, a.atttypmod) AS data_type,
                           NOT a.attnotnull AS is_nullable,
                           pg_get_expr(d.adbin, d.adrelid) AS column_default,
                           a.attnum AS ordinal_position
                    FROM pg_attribute a
                    JOIN pg_class c ON c.oid = a.attrelid
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                    LEFT JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum
                    WHERE n.nspname = $1
                    AND c.relname = $2
                    AND a.attnum > 0
                    AND NOT a.attisdropped
                    ORDER BY a.attnum
                """
                col_rows = await conn.fetch(col_sql, schema, tname)

                # Get primary key
                pk_sql = """
                    SELECT a.attname
                    FROM pg_index i
                    JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
                    JOIN pg_class c ON c.oid = i.indrelid
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE i.indisprimary
                    AND c.relname = $1
                    AND n.nspname = $2
                """
                pk_rows = await conn.fetch(pk_sql, tname, schema)
                pk_name = pk_rows[0]["attname"] if pk_rows else None

                columns = []
                for cr in col_rows:
                    columns.append(ColumnInfo(
                        name=cr["column_name"],
                        data_type=cr["data_type"],
                        is_nullable=bool(cr["is_nullable"]),
                        column_default=cr["column_default"],
                        character_maximum_length=None,
                        is_primary_key=cr["column_name"] == pk_name,
                        ordinal_position=cr["ordinal_position"],
                    ))

                # Row count estimate
                count_sql = f"SELECT reltuples::bigint FROM pg_class WHERE relname = $1"
                count_row = await conn.fetchval(count_sql, tname)

                tables.append(TableInfo(
                    name=tname,
                    schema_name=schema,
                    columns=columns,
                    primary_key=pk_name,
                    row_count_estimate=int(count_row) if count_row else None,
                    comment=tr["comment"],
                ))

            # Get foreign keys using pg_catalog (avoids permission issues)
            fk_sql = """
                SELECT
                    cl_from.relname AS from_table,
                    att_from.attname AS from_column,
                    cl_to.relname AS to_table,
                    att_to.attname AS to_column,
                    con.conname AS constraint_name
                FROM pg_constraint con
                JOIN pg_class cl_from ON cl_from.oid = con.conrelid
                JOIN pg_class cl_to ON cl_to.oid = con.confrelid
                JOIN pg_namespace n ON n.oid = cl_from.relnamespace
                JOIN pg_attribute att_from ON att_from.attrelid = con.conrelid AND att_from.attnum = ANY(con.conkey)
                JOIN pg_attribute att_to ON att_to.attrelid = con.confrelid AND att_to.attnum = ANY(con.confkey)
                WHERE con.contype = 'f'
                AND n.nspname = $1
            """
            fk_rows = await conn.fetch(fk_sql, schema)
            fks = [
                ForeignKey(
                    from_table=r["from_table"],
                    from_column=r["from_column"],
                    to_table=r["to_table"],
                    to_column=r["to_column"],
                    constraint_name=r["constraint_name"],
                )
                for r in fk_rows
            ]

            return tables, fks
        finally:
            await conn.close()

    async def _introspect_duckdb(
        self, schema: str,
        exclude_tables: list[str] | None,
        include_tables: list[str] | None,
    ) -> tuple[list[TableInfo], list[ForeignKey]]:
        import duckdb

        conn = duckdb.connect(self._url)
        try:
            # Get tables
            where_clauses = [f"table_schema = '{schema}'"]
            if include_tables:
                in_list = ", ".join(f"'{t}'" for t in include_tables)
                where_clauses.append(f"table_name IN ({in_list})")
            elif exclude_tables:
                not_list = ", ".join(f"'{t}'" for t in exclude_tables)
                where_clauses.append(f"table_name NOT IN ({not_list})")

            where = " AND ".join(where_clauses)
            table_rows = conn.execute(
                f"SELECT table_name FROM information_schema.tables WHERE {where} ORDER BY table_name"
            ).fetchall()

            tables: list[TableInfo] = []
            for (tname,) in table_rows:
                col_rows = conn.execute(
                    f"SELECT column_name, data_type, is_nullable, column_default, "
                    f"character_maximum_length, ordinal_position "
                    f"FROM information_schema.columns "
                    f"WHERE table_schema = '{schema}' AND table_name = '{tname}' "
                    f"ORDER BY ordinal_position"
                ).fetchall()

                columns = []
                pk_name = None
                for cr in col_rows:
                    col_name, data_type, nullable, default, max_len, ordinal = cr
                    # DuckDB: first column or 'id' column as heuristic PK
                    is_pk = col_name.lower() == "id" or (ordinal == 1 and col_name.lower().endswith("_id"))
                    if is_pk and pk_name is None:
                        pk_name = col_name
                    columns.append(ColumnInfo(
                        name=col_name,
                        data_type=str(data_type),
                        is_nullable=nullable == "YES",
                        column_default=default,
                        character_maximum_length=max_len,
                        is_primary_key=is_pk,
                        ordinal_position=ordinal,
                    ))

                # Row count
                try:
                    count = conn.execute(f"SELECT COUNT(*) FROM {tname}").fetchone()
                    row_count = count[0] if count else None
                except Exception:
                    row_count = None

                tables.append(TableInfo(
                    name=tname,
                    schema_name=schema,
                    columns=columns,
                    primary_key=pk_name,
                    row_count_estimate=row_count,
                ))

            return tables, []  # DuckDB doesn't have FKs in information_schema
        finally:
            conn.close()

    async def _introspect_mysql(
        self, schema: str,
        exclude_tables: list[str] | None,
        include_tables: list[str] | None,
    ) -> tuple[list[TableInfo], list[ForeignKey]]:
        """MySQL introspection (requires aiomysql)."""
        try:
            import aiomysql
        except ImportError:
            raise ImportError("MySQL introspection requires aiomysql: pip install nexaql[mysql]")

        # Parse MySQL URL
        # mysql://user:pass@host:port/dbname
        from urllib.parse import urlparse
        parsed = urlparse(self._url)
        conn = await aiomysql.connect(
            host=parsed.hostname or "localhost",
            port=parsed.port or 3306,
            user=parsed.username or "root",
            password=parsed.password or "",
            db=parsed.path.lstrip("/") if parsed.path else schema,
        )
        try:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                db_name = parsed.path.lstrip("/") if parsed.path else schema

                # Get tables
                where_extra = ""
                if include_tables:
                    in_list = ", ".join(f"'{t}'" for t in include_tables)
                    where_extra = f" AND TABLE_NAME IN ({in_list})"
                elif exclude_tables:
                    not_list = ", ".join(f"'{t}'" for t in exclude_tables)
                    where_extra = f" AND TABLE_NAME NOT IN ({not_list})"

                await cur.execute(
                    f"SELECT TABLE_NAME, TABLE_COMMENT FROM information_schema.TABLES "
                    f"WHERE TABLE_SCHEMA = %s AND TABLE_TYPE = 'BASE TABLE'{where_extra}",
                    (db_name,)
                )
                table_rows = await cur.fetchall()

                tables: list[TableInfo] = []
                for tr in table_rows:
                    tname = tr["TABLE_NAME"]

                    await cur.execute(
                        "SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, COLUMN_DEFAULT, "
                        "CHARACTER_MAXIMUM_LENGTH, ORDINAL_POSITION, COLUMN_KEY "
                        "FROM information_schema.COLUMNS "
                        "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s ORDER BY ORDINAL_POSITION",
                        (db_name, tname)
                    )
                    col_rows = await cur.fetchall()

                    columns = []
                    pk_name = None
                    for cr in col_rows:
                        is_pk = cr["COLUMN_KEY"] == "PRI"
                        if is_pk and pk_name is None:
                            pk_name = cr["COLUMN_NAME"]
                        columns.append(ColumnInfo(
                            name=cr["COLUMN_NAME"],
                            data_type=cr["DATA_TYPE"],
                            is_nullable=cr["IS_NULLABLE"] == "YES",
                            column_default=cr["COLUMN_DEFAULT"],
                            character_maximum_length=cr["CHARACTER_MAXIMUM_LENGTH"],
                            is_primary_key=is_pk,
                            ordinal_position=cr["ORDINAL_POSITION"],
                        ))

                    tables.append(TableInfo(
                        name=tname,
                        schema_name=db_name,
                        columns=columns,
                        primary_key=pk_name,
                        comment=tr["TABLE_COMMENT"] or None,
                    ))

                # Get foreign keys
                await cur.execute(
                    "SELECT TABLE_NAME, COLUMN_NAME, REFERENCED_TABLE_NAME, "
                    "REFERENCED_COLUMN_NAME, CONSTRAINT_NAME "
                    "FROM information_schema.KEY_COLUMN_USAGE "
                    "WHERE TABLE_SCHEMA = %s AND REFERENCED_TABLE_NAME IS NOT NULL",
                    (db_name,)
                )
                fk_rows = await cur.fetchall()
                fks = [
                    ForeignKey(
                        from_table=r["TABLE_NAME"],
                        from_column=r["COLUMN_NAME"],
                        to_table=r["REFERENCED_TABLE_NAME"],
                        to_column=r["REFERENCED_COLUMN_NAME"],
                        constraint_name=r["CONSTRAINT_NAME"],
                    )
                    for r in fk_rows
                ]

                return tables, fks
        finally:
            conn.close()

    # ── Enum detection ───────────────────────────────────────────────

    async def _detect_enums(self, tables: list[TableInfo],
                            max_cardinality: int = 25,
                            sample_limit: int = 1000) -> dict[str, dict[str, list[str]]]:
        """Detect enum-like columns by sampling distinct values.

        Returns {table_name: {column_name: [values]}}.
        """
        result: dict[str, dict[str, list[str]]] = {}

        if self._db_type == "postgresql":
            import asyncpg
            conn = await asyncpg.connect(self._url)
            try:
                for table in tables:
                    candidates = [
                        c for c in table.columns
                        if _is_likely_enum(c.name) or c.data_type in ("character varying", "varchar", "text")
                    ]
                    for col in candidates:
                        try:
                            rows = await conn.fetch(
                                f"SELECT DISTINCT {col.name} FROM {table.schema_name}.{table.name} "
                                f"WHERE {col.name} IS NOT NULL "
                                f"ORDER BY {col.name} LIMIT {max_cardinality + 1}"
                            )
                            values = [str(r[col.name]) for r in rows]
                            if 2 <= len(values) <= max_cardinality:
                                result.setdefault(table.name, {})[col.name] = values
                        except Exception:
                            continue
            finally:
                await conn.close()

        elif self._db_type == "duckdb":
            import duckdb
            conn = duckdb.connect(self._url)
            try:
                for table in tables:
                    candidates = [
                        c for c in table.columns
                        if _is_likely_enum(c.name) or "varchar" in c.data_type.lower()
                    ]
                    for col in candidates:
                        try:
                            rows = conn.execute(
                                f"SELECT DISTINCT {col.name} FROM {table.name} "
                                f"WHERE {col.name} IS NOT NULL "
                                f"ORDER BY {col.name} LIMIT {max_cardinality + 1}"
                            ).fetchall()
                            values = [str(r[0]) for r in rows]
                            if 2 <= len(values) <= max_cardinality:
                                result.setdefault(table.name, {})[col.name] = values
                        except Exception:
                            continue
            finally:
                conn.close()

        return result

    # ── Generation ───────────────────────────────────────────────────

    async def generate(
        self,
        schema: str = "public",
        domain: str = "auto_generated",
        description: str = "Auto-generated ontology from database schema",
        version: str = "1.0.0",
        exclude_tables: list[str] | None = None,
        include_tables: list[str] | None = None,
        detect_enums: bool = True,
        detect_pii: bool = True,
        include_system_columns: bool = False,
    ) -> Ontology:
        """Generate a complete NexaQL ontology from the database schema.

        Args:
            schema: Database schema to introspect (default: 'public').
            domain: Domain name for the ontology.
            description: Human-readable description.
            version: Ontology version string.
            exclude_tables: Tables to exclude from generation.
            include_tables: Only include these tables (if set, overrides exclude).
            detect_enums: Sample columns to detect enum values.
            detect_pii: Use heuristics to flag PII columns.
            include_system_columns: Include system columns (created_at, etc.).

        Returns:
            A fully populated Ontology model.
        """
        # Auto-exclude NexaQL system tables
        _SYSTEM_TABLES = {"nexaql_ontologies"}
        if not include_tables:
            exclude_tables = list(set(exclude_tables or []) | _SYSTEM_TABLES)

        # Introspect
        tables, foreign_keys = await self.introspect(schema, exclude_tables, include_tables)

        # Detect enums if requested
        enum_values: dict[str, dict[str, list[str]]] = {}
        if detect_enums:
            enum_values = await self._detect_enums(tables)

        # Build FK lookup: from_table → list[ForeignKey]
        fk_by_table: dict[str, list[ForeignKey]] = {}
        for fk in foreign_keys:
            fk_by_table.setdefault(fk.from_table, []).append(fk)

        # Build reverse FK lookup: to_table → list[ForeignKey] (for reverse edges)
        reverse_fk: dict[str, list[ForeignKey]] = {}
        for fk in foreign_keys:
            reverse_fk.setdefault(fk.to_table, []).append(fk)

        # Track table → node name mapping
        table_to_node: dict[str, str] = {}
        for t in tables:
            table_to_node[t.name] = _table_to_node_name(t.name)

        # Build nodes
        nodes: dict[str, OntologyNode] = {}

        for table in tables:
            node_name = table_to_node[table.name]

            # Build fields
            fields: dict[str, FieldDef] = {}
            for col in table.columns:
                if col.is_primary_key:
                    continue  # PK is separate in the ontology

                if not include_system_columns and col.name in _SYSTEM_COLUMNS:
                    continue

                # Skip FK columns (they become edges instead)
                table_fks = fk_by_table.get(table.name, [])
                if any(fk.from_column == col.name for fk in table_fks):
                    continue

                # Determine type
                field_type = _map_type(col.data_type)

                # Check for enum
                values = None
                table_enums = enum_values.get(table.name, {})
                if col.name in table_enums:
                    field_type = "enum"
                    values = table_enums[col.name]

                # Build field def
                field_def = FieldDef(
                    type=field_type,
                    description=_column_to_description(col.name, table.name),
                    filterable=True,
                    values=values,
                )

                # PII detection
                if detect_pii and _is_pii(col.name):
                    field_def.pii = True
                    field_def.mask_with = "redact"

                fields[col.name] = field_def

            # Build edges from FKs
            edges: dict[str, OntologyEdge] = {}
            for fk in fk_by_table.get(table.name, []):
                target_node = table_to_node.get(fk.to_table)
                if not target_node:
                    continue

                edge_name = _infer_edge_name(fk)
                # Avoid name collision with fields
                if edge_name in fields:
                    edge_name = f"{edge_name}_ref"

                # Determine join type based on nullability
                fk_col = next((c for c in table.columns if c.name == fk.from_column), None)
                join_type = "LEFT JOIN" if (fk_col and fk_col.is_nullable) else "JOIN"

                # Build alias for join
                alias = f"{target_node[0]}1"

                edges[edge_name] = OntologyEdge(
                    node=target_node,
                    description=f"Related {target_node}",
                    join_type=join_type,
                    join_steps=[JoinStep(
                        table=fk.to_table,
                        alias_key=alias,
                        condition=f"{alias}.{fk.to_column} = {node_name[0]}0.{fk.from_column}",
                    )],
                )

            # Build the node
            pk = table.primary_key or "id"
            node_desc = table.comment or f"{table.name.replace('_', ' ').title()} records"

            node = OntologyNode(
                table=table.name if table.name != node_name else None,
                description=node_desc,
                primary_key=pk,
                fields=fields,
                edges=edges if edges else None,
            )

            nodes[node_name] = node

        # Build datasource config
        datasources: dict[str, DatasourceConfig] = {}
        if self._db_type == "postgresql":
            datasources["default"] = PostgreSQLDatasource()
        elif self._db_type == "mysql":
            datasources["default"] = MySQLDatasource()
        elif self._db_type == "duckdb":
            datasources["default"] = DuckDBDatasource(path=self._url)

        return Ontology(
            version=version,
            domain=domain,
            description=description,
            datasources=datasources,
            nodes=nodes,
        )

    # ── Save ─────────────────────────────────────────────────────────

    def save(self, ontology: Ontology, path: str) -> None:
        """Save the generated ontology to a YAML file."""
        from nexaql.ontology.writer import save_ontology
        save_ontology(ontology, path)

    # ── LLM enrichment ───────────────────────────────────────────────

    def build_enrichment_prompt(self, ontology: Ontology) -> str:
        """Generate an LLM prompt for enriching the generated ontology.

        The LLM adds:
        - Human-readable descriptions for tables and columns
        - Identifies additional PII fields
        - Suggests access policies
        - Recommends special filters
        """
        lines = [
            "I have auto-generated a NexaQL ontology from a database schema.",
            "Please enrich it with better descriptions and access recommendations.",
            "",
            "For each node and field, provide:",
            "1. A clear, human-readable description (not just the column name reformatted)",
            "2. Whether the field is PII (personally identifiable information)",
            "3. Suggested access level: public, internal, restricted, confidential",
            "4. Suggested special filters that would be useful for querying",
            "",
            "Return JSON with the enrichments.",
            "",
            "## Current Ontology",
            "",
        ]

        for name, node in ontology.nodes.items():
            lines.append(f"### Node: {name}")
            lines.append(f"Table: {node.table or name}")
            lines.append(f"Description: {node.description}")
            lines.append("Fields:")
            for fname, fdef in node.fields.items():
                pii_tag = " [PII]" if fdef.pii else ""
                vals = f" (values: {fdef.values})" if fdef.values else ""
                lines.append(f"  - {fname} ({fdef.type}){pii_tag}: {fdef.description}{vals}")
            if node.edges:
                lines.append("Edges:")
                for ename, edef in node.edges.items():
                    lines.append(f"  - {ename} → {edef.node}")
            lines.append("")

        return "\n".join(lines)
