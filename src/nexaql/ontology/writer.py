# Copyright (c) 2026-present NexaQL Contributors
"""YAML serializer for NexaQL ontology definitions."""

from __future__ import annotations

from typing import Any

import yaml

from nexaql.ontology.models import Ontology
from nexaql.ontology.loader import invalidate_cache


def _strip_empty(obj: Any) -> Any:
    """Recursively strip None values, empty dicts, and empty lists."""
    if isinstance(obj, dict):
        cleaned = {}
        for k, v in obj.items():
            v = _strip_empty(v)
            if v is None or v == {} or v == []:
                continue
            cleaned[k] = v
        return cleaned
    if isinstance(obj, list):
        return [_strip_empty(item) for item in obj]
    return obj


def save_ontology(ontology: Ontology, path: str) -> None:
    """Save ontology to YAML, stripping None values for clean output."""
    data = ontology.model_dump(exclude_none=True)
    data = _strip_empty(data)

    yaml_str = yaml.dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True)

    with open(path, "w") as f:
        f.write("# NexaQL Ontology — managed by NexaQL Admin\n")
        f.write(yaml_str)

    invalidate_cache(path)
