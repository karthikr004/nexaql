"""YAML ontology loader with file-mtime caching."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

import yaml

from .models import Ontology

# ── Cache entry ──────────────────────────────────────────────────────────────


@dataclass
class _CacheEntry:
    mtime: float
    ontology: Ontology


_cache: dict[str, _CacheEntry] = {}


# ── Public API ───────────────────────────────────────────────────────────────


def load_ontology(path: str) -> Ontology:
    """Load and validate an ontology YAML file.

    Results are cached by absolute path and automatically invalidated when the
    file's modification time changes.
    """
    abs_path = os.path.abspath(path)
    mtime = os.path.getmtime(abs_path)

    cached = _cache.get(abs_path)
    if cached is not None and cached.mtime == mtime:
        return cached.ontology

    with open(abs_path) as f:
        raw = yaml.safe_load(f)

    ontology = Ontology(**raw)
    _cache[abs_path] = _CacheEntry(mtime=mtime, ontology=ontology)
    return ontology


def invalidate_cache(path: Optional[str] = None) -> None:
    """Clear the ontology cache.

    If *path* is given, only that entry is removed; otherwise the entire cache
    is flushed.
    """
    if path is not None:
        abs_path = os.path.abspath(path)
        _cache.pop(abs_path, None)
    else:
        _cache.clear()
