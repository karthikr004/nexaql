# Copyright (c) 2026-present NexaQL Contributors
"""Privacy and policy enforcement for NexaQL queries."""

from nexaql.policy.context import ANONYMOUS, UserContext, has_role
from nexaql.policy.enforcer import EnforcementResult, enforce_access
from nexaql.policy.masking import MaskRule, mask_results

__all__ = [
    "UserContext",
    "ANONYMOUS",
    "enforce_access",
    "EnforcementResult",
    "mask_results",
    "MaskRule",
    "has_role",
]
