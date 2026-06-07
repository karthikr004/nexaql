# Copyright (c) 2026-present NexaQL Contributors
"""Data models for the universal document taxonomy.

The taxonomy is a three-level hierarchy:

    Category  (broad domain)
      -> Type     (specific document kind)
          -> Subtype  (variant within a type)

Each type defines:
- **Entity template**: what structured fields to extract from the document
- **Context tier definitions**: how to build T1/T2/T3 context
- **Metadata schema**: what fields to persist for querying via NexaQL

Communications (email, chat) additionally define:
- **Intent classification**: map messages to intents (approval, question, escalation)
- **Entity linking**: how to attach message context to related documents
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


# ── Category enum ────────────────────────────────────────────────────────────


class DocCategory(str, Enum):
    """Top-level document category."""

    FINANCIAL = "financial"
    LEGAL = "legal"
    COMMUNICATION = "communication"
    OPERATIONAL = "operational"
    PERSONAL = "personal"
    REFERENCE = "reference"


# ── Entity extraction ────────────────────────────────────────────────────────


class EntityFieldDef(BaseModel):
    """Definition of a single entity field to extract from a document."""

    type: Literal["string", "integer", "numeric", "boolean", "date", "enum", "list", "money", "duration"]
    description: str
    required: bool = False
    enum_values: Optional[list[str]] = None
    extraction_hint: Optional[str] = None
    """Hint for the LLM extractor, e.g. 'Look in the header or first paragraph'"""


class EntityTemplate(BaseModel):
    """What structured entities to extract from a document of this type.

    The fields dict maps field_name -> EntityFieldDef. These become
    structured columns queryable via NexaQL once extracted.
    """

    fields: dict[str, EntityFieldDef]
    extraction_prompt: Optional[str] = None
    """Optional LLM system prompt tailored for this doc type's extraction."""


# ── Context tiers ────────────────────────────────────────────────────────────


class LinkStrategy(BaseModel):
    """How to find related documents for cross-doc or entity-level context."""

    match_fields: list[str]
    """Fields to match on (e.g. ['supplier_name', 'contract_id'])."""

    match_types: Optional[list[str]] = None
    """Doc types to search across (e.g. ['financial.invoice', 'legal.contract']).
    None means search all types."""

    temporal_window: Optional[str] = None
    """Time window for relevance (e.g. '90d', '1y', 'same_fiscal_year')."""

    relationship: Optional[str] = None
    """Semantic relationship (e.g. 'parent_child', 'references', 'same_entity')."""


class ContextTierDef(BaseModel):
    """Definition of a context tier (T1, T2, or T3) for a document type.

    - T1 (doc level): Understanding of this single document
    - T2 (cross-doc): Relationships between related documents
    - T3 (entity level): Full context for the primary entity
    """

    tier: Literal["t1", "t2", "t3"]
    scope: Literal["document", "cross_document", "entity"]
    description: str

    group_by: list[str]
    """Fields that define the grouping for this tier.
    T1: typically ['doc_id']
    T2: e.g. ['contract_id'] to group MSA + SOWs + amendments
    T3: e.g. ['supplier_name'] to group all docs for a supplier
    """

    link_strategy: Optional[LinkStrategy] = None
    """How to find related documents. Not needed for T1 (self-contained)."""

    context_prompt: str
    """LLM prompt template to generate this tier's context summary.
    Supports {placeholders} for extracted entity values.
    """

    output_fields: Optional[list[str]] = None
    """Structured fields to extract from the generated context.
    These become queryable alongside entity template fields.
    """


# ── Communication-specific models ────────────────────────────────────────────


class MessageIntentDef(BaseModel):
    """Intent classification for communication messages (email, chat)."""

    intent: str
    """Intent name (e.g. 'approval_request', 'question', 'escalation', 'decision')."""

    description: str
    """What this intent means."""

    indicators: list[str]
    """Natural language indicators (e.g. 'please approve', 'can you sign off')."""

    link_to_types: Optional[list[str]] = None
    """Doc types this intent commonly relates to.
    E.g. 'approval_request' often links to contracts or invoices.
    """

    action_required: bool = False
    """Whether this intent implies someone needs to act."""


# ── Subtype definition ───────────────────────────────────────────────────────


class DocSubtypeDef(BaseModel):
    """Variant of a document type with optional overrides.

    A subtype inherits entity_template and context_tiers from its parent
    type but can override or extend them.
    """

    name: str
    description: str
    classification_hints: list[str]
    """Keywords, patterns, or structural indicators for classification.
    E.g. ['Master Service Agreement', 'MSA', 'general terms and conditions']
    """

    extra_fields: Optional[dict[str, EntityFieldDef]] = None
    """Additional entity fields specific to this subtype (merged with parent)."""

    context_overrides: Optional[dict[str, ContextTierDef]] = None
    """Override specific context tiers for this subtype."""


# ── Top-level doc type definition ────────────────────────────────────────────


class DocTypeDef(BaseModel):
    """Full definition of a document type in the taxonomy.

    This is the primary unit registered in the DocTypeRegistry.
    """

    category: DocCategory
    type_name: str
    """Short identifier (e.g. 'invoice', 'contract', 'email')."""

    description: str
    """Human-readable description of this document type."""

    classification_hints: list[str]
    """Keywords, patterns, or structural indicators for auto-classification.
    E.g. ['Invoice', 'Bill To', 'Amount Due', 'Payment Terms']
    """

    subtypes: dict[str, DocSubtypeDef] = Field(default_factory=dict)
    """Named subtypes (e.g. 'msa', 'sow', 'amendment' for contracts)."""

    entity_template: EntityTemplate
    """What to extract from documents of this type."""

    context_tiers: dict[str, ContextTierDef]
    """T1/T2/T3 context generation definitions."""

    message_intents: Optional[list[MessageIntentDef]] = None
    """For communication types: intent classification definitions."""

    queryable_as: Optional[str] = None
    """NexaQL node name when entities are persisted as structured data.
    E.g. 'contract_doc' -> users can query: { contract_doc { title, supplier_name } }
    """

    parent_type: Optional[str] = None
    """Qualified parent type for inheritance (e.g. 'legal.contract')."""

    @property
    def qualified_name(self) -> str:
        """Full qualified name: 'category.type_name'."""
        return f"{self.category.value}.{self.type_name}"

    def resolve_subtype(self, subtype_name: str) -> DocSubtypeDef | None:
        """Look up a subtype by name."""
        return self.subtypes.get(subtype_name)

    def get_full_entity_template(self, subtype_name: str | None = None) -> EntityTemplate:
        """Get the entity template, merging subtype extra fields if applicable."""
        base_fields = dict(self.entity_template.fields)
        if subtype_name and subtype_name in self.subtypes:
            extra = self.subtypes[subtype_name].extra_fields
            if extra:
                base_fields.update(extra)
        return EntityTemplate(
            fields=base_fields,
            extraction_prompt=self.entity_template.extraction_prompt,
        )

    def get_context_tier(self, tier: str, subtype_name: str | None = None) -> ContextTierDef | None:
        """Get a context tier, checking subtype overrides first."""
        if subtype_name and subtype_name in self.subtypes:
            overrides = self.subtypes[subtype_name].context_overrides
            if overrides and tier in overrides:
                return overrides[tier]
        return self.context_tiers.get(tier)


# ── Classification result ────────────────────────────────────────────────────


class ClassificationResult(BaseModel):
    """Result of classifying a document."""

    category: DocCategory
    type_name: str
    subtype: Optional[str] = None
    confidence: float = 0.0
    """0.0 to 1.0 confidence score."""

    reasoning: Optional[str] = None
    """Why this classification was chosen."""

    @property
    def qualified_name(self) -> str:
        parts = [self.category.value, self.type_name]
        if self.subtype:
            parts.append(self.subtype)
        return ".".join(parts)


# ── Discovered fields (open extraction) ────────────────────────────────────


class DiscoveredField(BaseModel):
    """A field discovered during open extraction that wasn't in the template.

    These are captured during the 'what did we miss?' pass and stored
    alongside template-extracted entities. If a discovered field appears
    frequently across documents of a type, the evolution pipeline may
    promote it to the template.
    """

    field_name: str
    """Normalized snake_case field name (e.g. 'early_payment_discount')."""

    value: Any
    """Extracted value."""

    inferred_type: Literal["string", "integer", "numeric", "boolean", "date", "enum", "list", "money", "duration"]
    """Best-guess field type based on the value."""

    importance: Literal["critical", "high", "medium", "low"] = "medium"
    """How important this field is to the document's meaning."""

    reasoning: Optional[str] = None
    """Why this field was flagged as important."""

    section_ref: Optional[str] = None
    """Which section of the document this was found in."""


# ── Extraction quality metrics ─────────────────────────────────────────────


class ExtractionQuality(BaseModel):
    """Metrics about how well the extraction covered a document.

    Used by the evolution pipeline to identify taxonomy gaps and
    track template effectiveness over time.
    """

    doc_id: str
    """Document this quality report is for."""

    doc_type: str
    """Qualified doc type (e.g. 'financial.invoice')."""

    subtype: Optional[str] = None

    # Template coverage
    template_fields_total: int
    """Total fields in the entity template."""

    template_fields_found: int
    """How many template fields had non-null values extracted."""

    template_fields_required_found: int
    """How many required fields were successfully extracted."""

    template_fields_required_total: int
    """Total required fields in the template."""

    coverage_ratio: float
    """template_fields_found / template_fields_total."""

    required_coverage_ratio: float
    """template_fields_required_found / template_fields_required_total."""

    # Confidence
    field_confidences: dict[str, float] = Field(default_factory=dict)
    """Per-field extraction confidence (0.0-1.0)."""

    avg_confidence: float = 0.0
    """Mean confidence across all extracted fields."""

    low_confidence_fields: list[str] = Field(default_factory=list)
    """Fields with confidence < 0.5."""

    # Discovery
    discovered_fields_count: int = 0
    """Number of fields found beyond the template."""

    discovered_fields: list[DiscoveredField] = Field(default_factory=list)
    """The actual discovered fields."""

    # Classification
    classification_confidence: float = 0.0
    """Confidence of the doc type classification itself."""

    @property
    def needs_review(self) -> bool:
        """Whether this extraction should be flagged for human review."""
        return (
            self.coverage_ratio < 0.5
            or self.required_coverage_ratio < 0.8
            or self.avg_confidence < 0.4
            or self.classification_confidence < 0.6
        )

    @property
    def taxonomy_gap_signal(self) -> bool:
        """Whether this suggests the taxonomy template is inadequate."""
        return (
            self.discovered_fields_count >= 3
            and any(d.importance in ("critical", "high") for d in self.discovered_fields)
        )


# ── Field groups (composable templates) ────────────────────────────────────


class FieldGroup(BaseModel):
    """A reusable group of entity fields that can be composed into templates.

    Instead of each doc type defining fields from scratch, common field
    patterns are defined once and composed. When a group is improved,
    all types using it benefit.

    Example groups: monetary_terms, temporal_terms, party_info, compliance.
    """

    group_name: str
    """Unique identifier (e.g. 'monetary_terms')."""

    description: str
    """What this field group represents."""

    fields: dict[str, EntityFieldDef]
    """Fields in this group."""

    applicable_categories: Optional[list[str]] = None
    """Which doc categories this group commonly applies to.
    None means universally applicable."""


# ── Model configuration ───────────────────────────────────────────────────


class ModelConfig(BaseModel):
    """Configuration for a model used in the extraction pipeline.

    Supports local models via Ollama, HuggingFace transformers,
    or remote APIs as fallback.
    """

    name: str
    """Model identifier (e.g. 'qwen2.5:7b-instruct', 'gliner-medium-v2.1')."""

    provider: Literal["ollama", "huggingface", "api", "spacy", "keyword", "regex"] = "ollama"
    """How to load/serve the model."""

    task: Literal["classification", "ner", "extraction", "embedding", "reranking", "resolution", "discovery"]
    """What pipeline step this model handles."""

    model_id: Optional[str] = None
    """HuggingFace model ID or Ollama model tag (if different from name)."""

    max_tokens: int = 4096
    """Max input tokens this model supports."""

    batch_size: int = 8
    """Batch size for inference."""

    device: Literal["cpu", "cuda", "mps", "auto"] = "auto"
    """Device for inference. 'auto' detects available hardware."""

    quantization: Optional[Literal["q4", "q5", "q8", "fp16", "fp32"]] = None
    """Quantization level (for Ollama/HF models)."""

    temperature: float = 0.0
    """Sampling temperature (for generative models)."""

    options: dict[str, Any] = Field(default_factory=dict)
    """Model-specific options."""


class PipelineConfig(BaseModel):
    """Full configuration for the document extraction pipeline.

    Defines which models to use for each step, thresholds, and
    behavioral settings.
    """

    # Model assignments
    #
    # Default stack (Ollama-first, per-step specialization):
    #   Classification: qwen3:4b (fast, accurate, Apache 2.0)
    #   Extraction:     qwen3:4b (or NuExtract 3 when available)
    #   Discovery:      qwen3:8b (reasoning + summarization)
    #
    # Falls back to GLiNER/regex when Ollama is not running.

    classifier: ModelConfig = Field(default_factory=lambda: ModelConfig(
        name="qwen3:4b",
        provider="ollama",
        task="classification",
        model_id="qwen3:4b",
    ))

    entity_extractor: ModelConfig = Field(default_factory=lambda: ModelConfig(
        name="qwen3:4b",
        provider="ollama",
        task="ner",
        model_id="qwen3:4b",
    ))

    discovery_llm: ModelConfig = Field(default_factory=lambda: ModelConfig(
        name="qwen3:8b",
        provider="ollama",
        task="discovery",
        max_tokens=32768,
        model_id="qwen3:8b",
    ))

    embedder: ModelConfig = Field(default_factory=lambda: ModelConfig(
        name="bge-m3",
        provider="huggingface",
        task="embedding",
        model_id="BAAI/bge-m3",
        max_tokens=8192,
    ))

    reranker: ModelConfig = Field(default_factory=lambda: ModelConfig(
        name="bge-reranker-v2-m3",
        provider="huggingface",
        task="reranking",
        model_id="BAAI/bge-reranker-v2-m3",
    ))

    # Thresholds
    classification_first_page_only: bool = True
    """Only use first page (512 tokens) for classification."""

    classification_confidence_threshold: float = 0.6
    """Below this, flag for review or try LLM fallback."""

    extraction_coverage_skip_discovery: float = 0.8
    """Skip open discovery if template coverage exceeds this."""

    entity_resolution_fuzzy_threshold: float = 0.85
    """Auto-merge entities above this similarity score."""

    entity_resolution_ambiguous_range: tuple[float, float] = (0.7, 0.85)
    """Similarity range that triggers LLM-assisted resolution."""

    # Behavioral
    defer_t2_t3: bool = True
    """Don't build T2/T3 context at ingestion — build on-demand."""

    max_doc_tokens: int = 50000
    """Max tokens per document before chunking."""

    chunk_size: int = 4096
    """Chunk size for large document extraction."""

    chunk_overlap: int = 512
    """Overlap between chunks."""
