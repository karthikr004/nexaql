# Copyright (c) 2026-present NexaQL Contributors
"""NexaQL MCP Server — Model Context Protocol connector for AI agents.

Start with:  nexaql mcp
"""

from __future__ import annotations

import asyncio
import json as _json
import os
from importlib import resources
from typing import Any

from mcp.server.fastmcp import FastMCP

from nexaql import bootstrap as bs
from nexaql.config import NexaQLConfig, load_config
from nexaql.ontology.models import Ontology
from nexaql.ontology.prompt import ontology_summary, ontology_to_prompt_text

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_config: NexaQLConfig | None = None
_ontology: Ontology | None = None


def _get_config() -> NexaQLConfig:
    global _config
    if _config is None:
        config_path = os.environ.get("NEXAQL_CONFIG", "nexaql.yaml")
        _config = load_config(config_path)

        # Inject API key from bootstrap DB if missing
        if _config.llm.provider and not _config.llm.api_key:
            saved_key = bs.get_api_key(_config.llm.provider)
            if saved_key:
                _config.llm.api_key = saved_key
    return _config


def _get_ontology(domain: str | None = None) -> Ontology:
    global _ontology
    if _ontology is None or domain:
        from nexaql.api.deps import load_ontology_from_dict
        target = domain or bs.get_active_domain() or "default"
        ont_data = bs.get_domain_ontology(target)
        if ont_data:
            _ontology = load_ontology_from_dict(ont_data)
        else:
            raise ValueError(f"No ontology found for domain '{target}'")
    return _ontology


def _invalidate_cache() -> None:
    global _ontology, _config
    _ontology = None
    _config = None


def _resolve_user(
    auth_token: str | None = None,
    user_context: dict[str, Any] | None = None,
) -> "UserContext | dict[str, Any]":
    """Resolve user identity from auth_token (JWT) or raw user_context dict.

    Returns a UserContext on success, or a dict with an 'error' key on failure.
    """
    from nexaql.auth import AuthError, resolve_user_context
    try:
        return resolve_user_context(auth_token=auth_token, user_context=user_context)
    except AuthError as e:
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------

mcp = FastMCP(
    "NexaQL",
    instructions="Query any database with natural language. NexaQL translates questions into deterministic queries with built-in privacy enforcement.",
)


# ── Tools ──────────────────────────────────────────────────────────────────


@mcp.tool()
async def ask(
    question: str,
    domain: str | None = None,
    auth_token: str | None = None,
    user_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Ask a natural language question about your data.

    Translates the question into a NexaQL query, executes it, and returns
    results with a natural language summary. Access control and PII masking
    are applied based on the caller's identity.

    Args:
        question: Natural language question (e.g. "top 5 customers by revenue")
        domain: Optional domain name. Uses active domain if not specified.
        auth_token: Signed JWT token containing user claims (required when
            auth_mode is 'jwt'). The token payload should include 'sub' (user ID),
            'roles', and any attributes needed for row-level security.
        user_context: Raw user identity dict (only accepted in dev mode). Example:
            {"user_id": "alice", "roles": ["analyst"], "region": "US-EAST"}
            Use the user_context_schema tool to see supported fields.
    """
    user = _resolve_user(auth_token=auth_token, user_context=user_context)
    if isinstance(user, dict):
        return user

    cfg = _get_config()
    ontology = _get_ontology(domain)

    if not cfg.llm.provider or not cfg.llm.model:
        return {"error": "LLM not configured. Add an API key via the admin panel or nexaql.yaml."}

    if cfg.llm.provider.lower() != "ollama" and not cfg.llm.api_key:
        return {"error": f"API key required for provider '{cfg.llm.provider}'."}

    from nexaql.adapters import get_adapter
    from nexaql.chat.agent import ask as chat_ask

    adapter = None
    if cfg.datasources:
        try:
            adapter = get_adapter(next(iter(cfg.datasources.values())))
        except Exception:
            pass

    result = await chat_ask(
        question=question,
        history=[],
        ontology=ontology,
        adapter=adapter,
        llm_config=cfg.llm,
        user=user,
    )

    return {
        "summary": result.summary,
        "nexaql_query": result.nexaql_query,
        "sql_preview": result.query_preview,
        "rows": result.rows,
        "columns": [{"name": c.name, "type": c.type} for c in (result.columns or [])],
        "row_count": result.row_count,
        "error": result.error,
    }


@mcp.tool()
async def query(
    nexaql_query: str,
    auth_token: str | None = None,
    user_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute a NexaQL query and return results.

    Access control (RBAC, field-level security, RLS) and PII masking are
    applied based on the caller's identity.

    Args:
        nexaql_query: A NexaQL query string (e.g. '{ customer @limit(10) { name email } }')
        auth_token: Signed JWT token (required when auth_mode is 'jwt').
        user_context: Raw user identity dict (dev mode only).
    """
    ontology = _get_ontology()
    cfg = _get_config()

    from nexaql.adapters import get_adapter
    from nexaql.engine.parser import ParseError, parse
    from nexaql.engine.validator import validate
    from nexaql.policy import enforce_access, mask_results

    try:
        ast = parse(nexaql_query)
    except ParseError as e:
        return {"error": f"Parse error: {e}"}

    user = _resolve_user(auth_token=auth_token, user_context=user_context)
    if isinstance(user, dict):
        return user
    enforcement = enforce_access(ast, ontology, user)
    if enforcement.denied:
        return {"error": f"Access denied: {enforcement.denied_reason}"}

    validation = validate(enforcement.ast, ontology)
    if not validation.valid:
        return {
            "error": "Validation failed",
            "details": [err.message for err in validation.errors],
        }

    root_node = enforcement.ast.body.name
    node_def = ontology.nodes.get(root_node)
    ds_name = getattr(node_def, "datasource", None) if node_def else None

    if cfg.datasources:
        ds_cfg = cfg.datasources.get(ds_name or "default") or next(iter(cfg.datasources.values()))
        adapter = get_adapter(ds_cfg)
    else:
        return {"error": "No datasource configured"}

    result = await adapter.execute(enforcement.ast, ontology)
    rows = result.rows
    if enforcement.masked_fields:
        rows = mask_results(rows, enforcement.masked_fields)

    return {
        "sql_preview": result.query_preview,
        "adapter_type": result.adapter_type,
        "rows": rows,
        "columns": [{"name": c.name, "type": c.type} for c in result.columns],
        "row_count": result.row_count,
    }


@mcp.tool()
async def validate_query(
    nexaql_query: str,
    auth_token: str | None = None,
    user_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate a NexaQL query and preview the SQL without executing.

    Args:
        nexaql_query: A NexaQL query string to validate
        auth_token: Signed JWT token (required when auth_mode is 'jwt').
        user_context: Raw user identity dict (dev mode only).
    """
    ontology = _get_ontology()
    cfg = _get_config()

    from nexaql.adapters import get_adapter
    from nexaql.engine.parser import ParseError, parse
    from nexaql.engine.validator import validate
    from nexaql.policy import enforce_access

    try:
        ast = parse(nexaql_query)
    except ParseError as e:
        return {"valid": False, "errors": [str(e)]}

    user = _resolve_user(auth_token=auth_token, user_context=user_context)
    if isinstance(user, dict):
        return user
    enforcement = enforce_access(ast, ontology, user)

    validation = validate(enforcement.ast, ontology)
    sql_preview = None
    adapter_type = None
    if validation.valid and cfg.datasources:
        try:
            root_node = enforcement.ast.body.name
            node_def = ontology.nodes.get(root_node)
            ds_name = getattr(node_def, "datasource", None) if node_def else None
            ds_cfg = cfg.datasources.get(ds_name or "default") or next(iter(cfg.datasources.values()))
            adapter = get_adapter(ds_cfg)
            from nexaql.engine.translator import translate
            tr = translate(enforcement.ast, ontology)
            sql_preview = tr.sql
            adapter_type = ds_cfg.type
        except Exception:
            pass

    return {
        "valid": validation.valid,
        "errors": [err.message for err in validation.errors],
        "warnings": validation.warnings,
        "sql_preview": sql_preview,
        "adapter_type": adapter_type,
    }


@mcp.tool()
async def list_domains() -> dict[str, Any]:
    """List all available data domains."""
    active = bs.get_active_domain()
    domains = []
    for d in bs.list_domains():
        name = d["name"]
        schemas = bs.list_schemas(name)
        node_count = 0
        for s in schemas:
            try:
                ont_data = _json.loads(s.get("ontology_json", "{}"))
                node_count += len(ont_data.get("nodes", {}))
            except Exception:
                pass
        domains.append({
            "name": name,
            "description": d.get("description", ""),
            "node_count": node_count,
            "active": name == active,
        })
    return {"domains": domains, "active_domain": active}


@mcp.tool()
async def switch_domain(domain: str) -> dict[str, Any]:
    """Switch to a different data domain.

    Args:
        domain: The domain name to switch to
    """
    d = bs.get_domain(domain)
    if not d:
        return {"error": f"Domain '{domain}' not found"}
    schemas = bs.list_schemas(domain)
    if not schemas:
        return {"error": f"Domain '{domain}' has no schemas"}

    bs.set_active_domain(domain)
    _invalidate_cache()

    ontology = _get_ontology(domain)
    return {
        "status": "switched",
        "domain": domain,
        "nodes": list(ontology.nodes.keys()),
        "node_count": len(ontology.nodes),
    }


@mcp.tool()
async def describe_node(node_name: str) -> dict[str, Any]:
    """Describe a specific node — its fields, types, edges, and filters.

    Args:
        node_name: Name of the node to describe (e.g. "customer", "order")
    """
    ontology = _get_ontology()
    defn = ontology.nodes.get(node_name)
    if not defn:
        available = list(ontology.nodes.keys())
        return {"error": f"Node '{node_name}' not found. Available: {available}"}

    fields = []
    for fname, fdef in defn.fields.items():
        f: dict[str, Any] = {
            "name": fname,
            "type": fdef.type,
            "filterable": fdef.filterable or False,
        }
        if fdef.description:
            f["description"] = fdef.description
        if fdef.values:
            f["enum_values"] = fdef.values
        if fdef.pii:
            f["pii"] = True
        if fdef.visible_to:
            f["visible_to"] = fdef.visible_to
        fields.append(f)

    edges = []
    for ename, edef in (defn.edges or {}).items():
        edges.append({
            "name": ename,
            "target_node": edef.node,
            "description": edef.description,
        })

    special_filters = []
    for sname, sdef in (defn.special_filters or {}).items():
        special_filters.append({
            "name": sname,
            "description": sdef.description,
        })

    result: dict[str, Any] = {
        "node": node_name,
        "table": defn.table,
        "fields": fields,
        "edges": edges,
    }
    if special_filters:
        result["special_filters"] = special_filters
    if defn.visible_to:
        result["visible_to"] = defn.visible_to
    return result


@mcp.tool()
async def describe_ontology() -> dict[str, Any]:
    """Get a full summary of the current domain's ontology — all nodes, fields, edges, and relationships."""
    ontology = _get_ontology()
    return ontology_summary(ontology)


@mcp.tool()
async def list_connectors() -> dict[str, Any]:
    """List configured database connectors."""
    connectors = []
    for c in bs.list_connectors():
        connectors.append({
            "name": c["name"],
            "type": c["type"],
            "id": c["id"],
        })
    return {"connectors": connectors}


@mcp.tool()
async def user_context_schema() -> dict[str, Any]:
    """Describe the user context fields supported by this NexaQL instance.

    Returns the standard fields, the current auth mode, which roles are
    defined in the ontology, and which user attributes are referenced by
    row-level security policies (so you know which claims your JWT must include).
    """
    from nexaql.auth import get_auth_config
    from nexaql.policy.context import CANONICAL_FIELDS

    auth = get_auth_config()
    ontology = _get_ontology()

    # Collect user attributes referenced by RLS policies
    rls_attributes: set[str] = set()
    import re
    placeholder_re = re.compile(r"\{user\.(\w+)\}")
    for _name, defn in ontology.nodes.items():
        for policy in (defn.row_policies or []):
            fn_name = policy.function if hasattr(policy, "function") else None
            if fn_name and ontology.access_functions:
                fn = ontology.access_functions.get(fn_name)
                if fn and fn.sql:
                    rls_attributes.update(placeholder_re.findall(fn.sql))

    roles = {}
    if ontology.roles:
        roles = {name: role.description for name, role in ontology.roles.items()}

    standard_fields = [
        {"name": "user_id", "type": "string", "description": "Unique user identifier (maps to JWT 'sub' claim)"},
        {"name": "roles", "type": "list[string]", "description": "User roles for RBAC (e.g. ['analyst', 'manager'])"},
        {"name": "name", "type": "string", "description": "Display name"},
        {"name": "email", "type": "string", "description": "Email address"},
        {"name": "manager_id", "type": "string", "description": "Manager's user ID"},
        {"name": "region", "type": "string", "description": "Geographic region (e.g. 'US-EAST')"},
        {"name": "department", "type": "string", "description": "Department name"},
        {"name": "team_id", "type": "string", "description": "Team identifier"},
        {"name": "level", "type": "string", "description": "Seniority level"},
        {"name": "job_role", "type": "string", "description": "Job title/role"},
        {"name": "org_id", "type": "string", "description": "Organization identifier"},
    ]

    result: dict[str, Any] = {
        "auth_mode": auth["auth_mode"],
        "auth_algorithm": auth["auth_algorithm"],
        "standard_fields": standard_fields,
        "defined_roles": roles,
    }

    if rls_attributes:
        result["rls_required_attributes"] = sorted(rls_attributes)
        result["rls_note"] = (
            "These attributes are referenced by row-level security policies. "
            "Include them in your JWT claims or user_context for RLS to work correctly."
        )

    if auth["auth_mode"] == "jwt":
        result["jwt_claims_mapping"] = {
            "sub": "Maps to user_id",
            "roles": "List of role strings",
            "Custom claims": "Any additional claim becomes a user attribute for RLS",
        }
        result["note"] = "auth_mode is 'jwt' — pass auth_token (signed JWT) with every request. Raw user_context is rejected."
    else:
        result["note"] = (
            "auth_mode is 'dev' — raw user_context dicts are accepted (no signature verification). "
            "Switch to 'jwt' mode for production by calling configure_auth."
        )

    return result


@mcp.tool()
async def configure_auth(
    auth_mode: str,
    auth_secret: str | None = None,
    auth_algorithm: str = "HS256",
) -> dict[str, Any]:
    """Configure authentication mode for NexaQL.

    Args:
        auth_mode: 'dev' (trust raw user_context) or 'jwt' (require signed tokens).
        auth_secret: The secret key for JWT verification. Required for 'jwt' mode.
            For HS256: a shared secret string.
            For RS256/ES256: the public key in PEM format.
        auth_algorithm: JWT signing algorithm. Default 'HS256'.
            Supported: HS256, HS384, HS512, RS256, RS384, RS512, ES256, ES384, ES512.
    """
    if auth_mode not in ("dev", "jwt"):
        return {"error": "auth_mode must be 'dev' or 'jwt'"}

    if auth_mode == "jwt" and not auth_secret:
        return {"error": "auth_secret is required when auth_mode is 'jwt'"}

    bs.update_server_config(
        auth_mode=auth_mode,
        auth_secret=auth_secret,
        auth_algorithm=auth_algorithm,
    )
    _invalidate_cache()

    return {
        "status": "configured",
        "auth_mode": auth_mode,
        "auth_algorithm": auth_algorithm,
        "auth_secret_set": bool(auth_secret),
    }


@mcp.tool()
async def sql_preview(
    nexaql_query: str,
    auth_token: str | None = None,
    user_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Translate a NexaQL query to native SQL without executing it.

    Shows the SQL that would run after access control enforcement, so the
    output reflects field stripping and RLS injection for the given user.

    Args:
        nexaql_query: A NexaQL query string to translate
        auth_token: Signed JWT token (required when auth_mode is 'jwt').
        user_context: Raw user identity dict (dev mode only).
    """
    ontology = _get_ontology()
    cfg = _get_config()

    from nexaql.adapters import get_adapter
    from nexaql.engine.parser import ParseError, parse
    from nexaql.engine.translator import translate
    from nexaql.engine.validator import validate
    from nexaql.policy import enforce_access

    try:
        ast = parse(nexaql_query)
    except ParseError as e:
        return {"error": f"Parse error: {e}"}

    user = _resolve_user(auth_token=auth_token, user_context=user_context)
    if isinstance(user, dict):
        return user
    enforcement = enforce_access(ast, ontology, user)

    validation = validate(enforcement.ast, ontology)
    if not validation.valid:
        return {"error": "Validation failed", "details": [err.message for err in validation.errors]}

    if not cfg.datasources:
        return {"error": "No datasource configured"}

    root_node = enforcement.ast.body.name
    node_def = ontology.nodes.get(root_node)
    ds_name = getattr(node_def, "datasource", None) if node_def else None
    ds_cfg = cfg.datasources.get(ds_name or "default") or next(iter(cfg.datasources.values()))
    adapter = get_adapter(ds_cfg)

    result = translate(enforcement.ast, ontology)
    return {
        "sql": result.sql,
        "adapter_type": ds_cfg.type,
    }


# ── Resources ──────────────────────────────────────────────────────────────


@mcp.resource("nexaql://ontology")
def resource_ontology() -> str:
    """Current domain's full ontology as structured JSON."""
    ontology = _get_ontology()
    return _json.dumps(ontology_summary(ontology), indent=2)


@mcp.resource("nexaql://grammar")
def resource_grammar() -> str:
    """NexaQL query syntax reference."""
    grammar_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "docs",
        "grammar.md",
    )
    if os.path.exists(grammar_path):
        with open(grammar_path) as f:
            return f.read()

    return """\
# NexaQL Grammar Reference

## Basic Query
{ node_name { field1 field2 } }

## Filters
{ node_name(field: "value") { field1 } }
{ node_name(field: { gt: 100 }) { field1 } }

## Edge Traversal
{ customer { name orders { total_amount } } }

## Aggregations
{ order { customer_id total: sum(total_amount) count: count() } }

## Directives
{ order @limit(10) @orderby(total_amount, DESC) { id total_amount } }

## Computed Fields
{ order_item { quantity unit_price line_total: calc(quantity * unit_price) } }
"""


@mcp.resource("nexaql://roles")
def resource_roles() -> str:
    """Available roles and access policies for the current domain."""
    ontology = _get_ontology()
    roles_info: dict[str, Any] = {}

    if ontology.roles:
        roles_info["roles"] = {
            name: {"description": role.description}
            for name, role in ontology.roles.items()
        }

    if ontology.access_functions:
        roles_info["access_functions"] = {
            name: {"description": fn.description}
            for name, fn in ontology.access_functions.items()
        }

    node_access = {}
    for name, defn in ontology.nodes.items():
        access: dict[str, Any] = {}
        if defn.visible_to:
            access["visible_to"] = defn.visible_to
        pii_fields = [
            fname for fname, fdef in defn.fields.items() if fdef.pii
        ]
        if pii_fields:
            access["pii_fields"] = pii_fields
        if access:
            node_access[name] = access

    if node_access:
        roles_info["node_access"] = node_access

    return _json.dumps(roles_info, indent=2)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def run_mcp(transport: str = "stdio") -> None:
    """Start the NexaQL MCP server."""
    mcp.run(transport=transport)


if __name__ == "__main__":
    run_mcp()
