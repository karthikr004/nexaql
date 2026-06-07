# Copyright (c) 2026-present NexaQL Contributors
"""Universal document taxonomy framework.

Provides a registry-based classification system for any document type,
with structured entity extraction templates and three-tier context
generation (T1: document-level, T2: cross-document, T3: entity-level).

Quick start::

    from nexaql.taxonomy import get_registry

    registry = get_registry()           # includes all built-in types
    doc_type = registry.resolve("legal.contract.msa")
    print(doc_type.entity_template)     # fields to extract
    print(doc_type.context_tiers["t1"]) # doc-level context definition

Custom types::

    from nexaql.taxonomy import DocTypeDef, get_registry

    registry = get_registry()
    registry.register(DocTypeDef(
        category="custom",
        type_name="design_spec",
        description="Product design specification",
        ...
    ))

Extraction pipeline (requires nexaql-pro)::

    from nexaql_pro.extractors import ExtractionPipeline
    from nexaql.taxonomy.models import PipelineConfig

    pipeline = ExtractionPipeline(PipelineConfig())
    pipeline.load()
    result = pipeline.process(doc_id="doc1", text="...")
"""

from nexaql.taxonomy.models import (
    ClassificationResult,
    ContextTierDef,
    DiscoveredField,
    DocCategory,
    DocSubtypeDef,
    DocTypeDef,
    EntityFieldDef,
    EntityTemplate,
    ExtractionQuality,
    FieldGroup,
    LinkStrategy,
    MessageIntentDef,
    ModelConfig,
    PipelineConfig,
)
from nexaql.taxonomy.registry import DocTypeRegistry, get_registry

__all__ = [
    # Core taxonomy models
    "ClassificationResult",
    "ContextTierDef",
    "DocCategory",
    "DocSubtypeDef",
    "DocTypeDef",
    "DocTypeRegistry",
    "EntityFieldDef",
    "EntityTemplate",
    "LinkStrategy",
    "MessageIntentDef",
    # Extraction & evolution
    "DiscoveredField",
    "ExtractionQuality",
    "FieldGroup",
    "ModelConfig",
    "PipelineConfig",
    # Registry
    "get_registry",
]
