# Copyright (c) 2026-present NexaQL Contributors
"""Core policy enforcer -- rewrites AST to enforce access control policies."""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from nexaql.engine.types import (
    AggregationField,
    CalcField,
    EdgeField,
    Field,
    Filter,
    FilterOp,
    NodeSelection,
    QueryAST,
    ScalarField,
)
from nexaql.policy.context import UserContext, has_role, resolve_user_value
from nexaql.policy.masking import MaskRule


@dataclass
class EnforcementResult:
    ast: QueryAST
    denied: bool = False
    denied_reason: Optional[str] = None
    masked_fields: List[MaskRule] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def enforce_access(
    ast: QueryAST,
    ontology: Any,
    user: UserContext,
) -> EnforcementResult:
    """Enforce access policies on *ast* for *user*.

    If the user has the wildcard role ``"*"``, the AST is returned unchanged
    (full access).  Otherwise each node and field is checked against the
    ontology's ``visible_to``, row-level security policies, and PII masking
    annotations.
    """
    if "*" in user.roles:
        return EnforcementResult(ast=ast)

    # Deep-copy the AST so enforcement never mutates the caller's original
    enforced_ast = copy.deepcopy(ast)

    masked_fields: List[MaskRule] = []
    warnings: List[str] = []

    error = _enforce_node(
        node=enforced_ast.body,
        ontology=ontology,
        user=user,
        masked_fields=masked_fields,
        warnings=warnings,
        parent_edge_def=None,
    )

    if error is not None:
        return EnforcementResult(
            ast=enforced_ast,
            denied=True,
            denied_reason=error,
            masked_fields=masked_fields,
            warnings=warnings,
        )

    return EnforcementResult(
        ast=enforced_ast,
        denied=False,
        masked_fields=masked_fields,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_PLACEHOLDER_RE = re.compile(r"\{user\.(\w+)\}")


def _resolve_placeholders(template: str, user: UserContext) -> str:
    """Replace ``{user.xxx}`` placeholders with properly typed values.

    - String values are escaped for SQL (single quotes handled)
    - Numeric values (int/float) are NOT quoted -- they produce bare numbers
    - None values produce empty string (with a warning)
    """

    def _replacer(m: re.Match) -> str:
        key = m.group(1)
        val = resolve_user_value(user, key)
        if val is None:
            return ""
        if isinstance(val, (int, float)):
            return str(val)
        return str(val).replace("'", "''")

    return _PLACEHOLDER_RE.sub(_replacer, template)


def _resolve_function_policy(policy: Any, ontology: Any, user: "UserContext") -> str:
    """Resolve a function-reference row policy into a concrete SQL condition.

    Looks up *policy.function* in ``ontology.access_functions``, substitutes
    ``{field}`` with *policy.field*, then resolves ``{user.xxx}`` placeholders.
    """
    func_name = getattr(policy, "function", None)
    field = getattr(policy, "field", None)

    access_functions = getattr(ontology, "access_functions", None) or {}
    func_def = access_functions.get(func_name) if access_functions else None

    if func_def is None:
        raise ValueError(
            f"Row policy references unknown access function '{func_name}'. "
            f"Available functions: {list(access_functions.keys())}"
        )

    if not field:
        raise ValueError(
            f"Row policy using access function '{func_name}' must specify a 'field'."
        )

    sql = func_def.sql.replace("{field}", field)
    return _resolve_placeholders(sql, user)


def _enforce_node(
    node: NodeSelection,
    ontology: Any,
    user: UserContext,
    masked_fields: List[MaskRule],
    warnings: List[str],
    parent_edge_def: Any = None,
) -> Optional[str]:
    """Enforce policies on a single *node*.  Returns an error string if the
    node is denied, or ``None`` if access is allowed.
    """

    nodes_map: Dict[str, Any] = getattr(ontology, "nodes", {}) or {}
    node_def = nodes_map.get(node.name)
    if node_def is None:
        # Unknown node -- let the validator catch this; pass through here.
        warnings.append(f"Policy enforcer: unknown node '{node.name}', skipping enforcement")
        return None

    # -- Step 1: Node-level access --------------------------------------------
    visible_to = getattr(node_def, "visible_to", None)
    if visible_to is not None and not has_role(user, visible_to):
        return (
            f"Access denied: node '{node.name}' requires one of roles "
            f"{visible_to}, but user '{user.user_id}' has roles {user.roles}"
        )

    # -- Step 2: Row-level security -------------------------------------------
    row_policies: List[Any] = getattr(node_def, "row_policies", []) or []
    for policy in row_policies:
        policy_roles = getattr(policy, "roles", None)
        except_roles = getattr(policy, "except_roles", None) or []

        # Policy applies when user matches .roles AND is NOT in .except_roles
        if not has_role(user, policy_roles):
            continue
        if set(user.roles) & set(except_roles):
            continue

        # Resolve the condition -- either raw or via a named access function
        func_name = getattr(policy, "function", None)
        condition = getattr(policy, "condition", None)

        if func_name is not None:
            resolved = _resolve_function_policy(policy, ontology, user)
        elif condition:
            resolved = _resolve_placeholders(condition, user)
        else:
            warnings.append(
                f"Row policy on '{node.name}' has neither 'condition' nor 'function'; skipping"
            )
            continue

        # Inject as a raw RLS filter — the translator will inject this as a
        # raw WHERE clause, qualifying only the node's own field names with the
        # table alias but NOT expanding subquery internals.
        rls_filter = Filter(
            field="__rls",
            op=FilterOp.EQ,
            value=resolved,
        )
        node.filters.append(rls_filter)

    # -- Step 3: Field-level access -------------------------------------------
    fields_map: Dict[str, Any] = getattr(node_def, "fields", {}) or {}
    edges_map: Dict[str, Any] = getattr(node_def, "edges", {}) or {}

    filtered_fields: List[Field] = []
    for fld in node.fields:
        if fld.kind == "scalar":
            scalar: ScalarField = fld  # type: ignore[assignment]
            field_def = fields_map.get(scalar.name)
            if field_def is not None:
                field_visible = getattr(field_def, "visible_to", None)
                if field_visible is not None and not has_role(user, field_visible):
                    mask_with = getattr(field_def, "mask_with", None)
                    pii = getattr(field_def, "pii", False)
                    if pii and mask_with:
                        alias = f"{node.name}__{scalar.name}"
                        masked_fields.append(MaskRule(column_alias=alias, strategy=mask_with))
                    else:
                        warnings.append(
                            f"Field '{scalar.name}' on '{node.name}' hidden from user "
                            f"'{user.user_id}' (requires roles {field_visible})"
                        )
                        continue

            filtered_fields.append(fld)

        elif fld.kind == "calc":
            # Computed fields are not restricted by default
            filtered_fields.append(fld)

        elif fld.kind == "aggregation":
            # Aggregation fields are not restricted by default
            filtered_fields.append(fld)

        elif fld.kind == "edge":
            edge: EdgeField = fld  # type: ignore[assignment]
            edge_name = edge.node.name
            edge_def = edges_map.get(edge_name)

            # Resolve the target node name (same pattern as validator/translator)
            target_node_name: Optional[str] = None
            if edge_def is not None:
                target_node_name = getattr(edge_def, "node", None) or (
                    edge_def.get("node") if isinstance(edge_def, dict) else None
                )

            if target_node_name:
                # Temporarily set the child node's name to the resolved target
                original_name = edge.node.name
                edge.node.name = target_node_name

                child_error = _enforce_node(
                    node=edge.node,
                    ontology=ontology,
                    user=user,
                    masked_fields=masked_fields,
                    warnings=warnings,
                    parent_edge_def=edge_def,
                )

                # Restore the edge name for the translator
                edge.node.name = original_name

                if child_error is not None:
                    warnings.append(
                        f"Edge '{edge_name}' on '{node.name}' removed: {child_error}"
                    )
                    continue  # skip entire edge
            else:
                # No target resolution -- recurse with the edge name as-is
                child_error = _enforce_node(
                    node=edge.node,
                    ontology=ontology,
                    user=user,
                    masked_fields=masked_fields,
                    warnings=warnings,
                    parent_edge_def=edge_def,
                )
                if child_error is not None:
                    warnings.append(
                        f"Edge '{edge_name}' on '{node.name}' removed: {child_error}"
                    )
                    continue

            filtered_fields.append(fld)

    node.fields = filtered_fields
    return None
