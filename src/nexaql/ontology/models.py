"""Pydantic v2 models for NexaQL ontology definitions."""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


# ── Datasource definitions ───────────────────────────────────────────────────


class RESTAuth(BaseModel):
    type: Literal["bearer", "apikey"]
    token_env: Optional[str] = None
    header: Optional[str] = None
    key_env: Optional[str] = None


class PostgreSQLDatasource(BaseModel):
    type: Literal["postgresql"] = "postgresql"


class SnowflakeDatasource(BaseModel):
    type: Literal["snowflake"] = "snowflake"
    account: Optional[str] = None
    warehouse: Optional[str] = None
    database: Optional[str] = None
    schema_: Optional[str] = Field(None, alias="schema")

    model_config = {"populate_by_name": True}


class PrestoDatasource(BaseModel):
    type: Literal["presto"] = "presto"
    host: Optional[str] = None
    port: Optional[int] = None
    catalog: Optional[str] = None
    schema_: Optional[str] = Field(None, alias="schema")

    model_config = {"populate_by_name": True}


class BigQueryDatasource(BaseModel):
    type: Literal["bigquery"] = "bigquery"
    project_id: Optional[str] = None
    dataset: Optional[str] = None


class SparkDatasource(BaseModel):
    type: Literal["spark"] = "spark"
    thrift_host: Optional[str] = None
    port: Optional[int] = None


class MySQLDatasource(BaseModel):
    type: Literal["mysql"] = "mysql"
    host: Optional[str] = None
    port: Optional[int] = None


class MSSQLDatasource(BaseModel):
    type: Literal["mssql"] = "mssql"
    host: Optional[str] = None
    port: Optional[int] = None


class RESTDatasource(BaseModel):
    type: Literal["rest"] = "rest"
    base_url: str
    headers: Optional[dict[str, str]] = None
    auth: Optional[RESTAuth] = None


class DuckDBDatasource(BaseModel):
    type: Literal["duckdb"] = "duckdb"
    path: Optional[str] = None


DatasourceConfig = (
    PostgreSQLDatasource
    | SnowflakeDatasource
    | PrestoDatasource
    | BigQueryDatasource
    | SparkDatasource
    | MySQLDatasource
    | MSSQLDatasource
    | RESTDatasource
    | DuckDBDatasource
)


# ── Node / field definitions ─────────────────────────────────────────────────


class AccessFunction(BaseModel):
    """A reusable, named access-policy function defined at the ontology level.

    The *sql* template may contain ``{field}`` (resolved to the column the
    policy targets) and ``{user.xxx}`` placeholders (resolved from user
    attributes at enforcement time).
    """

    description: str
    sql: str
    requires: Optional[list[str]] = None


class RowPolicy(BaseModel):
    """Row-level security policy.

    Supports two modes:
    * **Raw condition** -- set *condition* directly (existing / backward-compat).
    * **Function reference** -- set *function* (name of an ``AccessFunction``)
      and *field* (column the function applies to).
    """

    # Raw condition mode (existing):
    condition: Optional[str] = None
    # Function reference mode (new):
    function: Optional[str] = None
    field: Optional[str] = None
    # Common fields:
    roles: list[str]
    except_roles: Optional[list[str]] = None


class FieldDef(BaseModel):
    type: Literal["string", "integer", "numeric", "boolean", "date", "enum"]
    description: str
    filterable: Optional[bool] = None
    values: Optional[list[str]] = None
    derived: Optional[bool] = None
    sql_expr: Optional[str] = None
    visible_to: Optional[list[str]] = None
    pii: Optional[bool] = None
    mask_with: Optional[str] = None


class JoinStep(BaseModel):
    table: str
    alias_key: str
    condition: str


class OntologyEdge(BaseModel):
    node: str
    description: str
    join_type: Optional[Literal["JOIN", "LEFT", "LEFT JOIN"]] = None
    join_steps: list[JoinStep]


class SpecialFilter(BaseModel):
    description: str
    type: Optional[str] = None
    applies_when: Optional[str] = None
    requires_edge: Optional[str] = None
    sql: str


class OntologyNode(BaseModel):
    table: Optional[str] = None
    alias: Optional[str] = None
    description: str
    primary_key: str
    fields: dict[str, FieldDef]
    edges: Optional[dict[str, OntologyEdge]] = None
    special_filters: Optional[dict[str, SpecialFilter]] = None
    datasource: Optional[str] = None
    endpoint: Optional[str] = None
    rest_method: Optional[Literal["GET", "POST"]] = None
    response_path: Optional[str] = None
    filter_params: Optional[dict[str, str]] = None
    visible_to: Optional[list[str]] = None
    row_policies: Optional[list[RowPolicy]] = None


class Ontology(BaseModel):
    """Top-level ontology definition.

    Designed so that ``Ontology(**yaml.safe_load(open(path)))`` works directly.
    """

    version: str
    domain: str
    description: str
    datasources: Optional[dict[str, DatasourceConfig]] = None
    access_functions: Optional[dict[str, AccessFunction]] = None
    nodes: dict[str, OntologyNode]
