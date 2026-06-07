# Copyright (c) 2026-present NexaQL Contributors
"""Context tier framework — builds T1/T2/T3 context for documents.

The context builder takes parsed documents, their extracted entities,
and the taxonomy definitions to generate structured context at three
tiers:

- **T1 (Document Level)**: Understanding of a single document in isolation.
- **T2 (Cross-Document)**: Relationships between related documents
  (e.g., contract family: MSA → SOW → Amendment).
- **T3 (Entity Level)**: Complete context for a primary entity across
  all document types (e.g., full supplier profile).

The framework is generic — it doesn't know about specific doc types.
All behavior is driven by the taxonomy definitions (ContextTierDef,
LinkStrategy) registered in the DocTypeRegistry.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from nexaql.taxonomy.models import (
    ClassificationResult,
    ContextTierDef,
    DocTypeDef,
    LinkStrategy,
)


# ── Data structures ──────────────────────────────────────────────────────────


@dataclass
class DocumentRecord:
    """A parsed document with its classification and extracted entities.

    This is the input to the context builder — typically produced by the
    ingestion pipeline.
    """

    doc_id: str
    """Unique document identifier."""

    source: str
    """Source system (e.g., 'gmail', 'gdrive', 'slack', 'upload')."""

    source_ref: Optional[str] = None
    """Source-specific reference (e.g., Gmail message ID, GDrive file ID)."""

    raw_text: Optional[str] = None
    """Raw text content (or first N chars for large docs)."""

    classification: Optional[ClassificationResult] = None
    """Document classification result."""

    entities: dict[str, Any] = field(default_factory=dict)
    """Extracted entity values (field_name → value)."""

    sections: list[dict[str, Any]] = field(default_factory=list)
    """Parsed sections: [{'title': ..., 'content': ..., 'level': ...}]"""

    metadata: dict[str, Any] = field(default_factory=dict)
    """Additional metadata (file size, mime type, etc.)."""

    embeddings: Optional[list[list[float]]] = None
    """Pre-computed embeddings for this document's chunks."""

    chunk_texts: Optional[list[str]] = None
    """Text chunks used for embedding generation."""


@dataclass
class ContextResult:
    """Result of context generation for a single tier."""

    tier: str
    """'t1', 't2', or 't3'."""

    scope: str
    """'document', 'cross_document', or 'entity'."""

    doc_id: str
    """Primary document this context is for."""

    group_key: dict[str, Any]
    """The grouping key values (e.g., {'vendor_name': 'Acme Corp'})."""

    related_doc_ids: list[str]
    """IDs of related documents included in this context (empty for T1)."""

    context_summary: Optional[str] = None
    """LLM-generated context summary (populated after LLM call)."""

    structured_output: dict[str, Any] = field(default_factory=dict)
    """Structured fields extracted from the context."""

    input_prompt: Optional[str] = None
    """The prompt sent to the LLM (for debugging/auditability)."""


@dataclass
class LinkMatch:
    """A document that matched a link strategy."""

    doc_id: str
    qualified_type: str
    match_fields: dict[str, Any]
    relevance_score: float = 1.0


# ── Context builder ──────────────────────────────────────────────────────────


class ContextBuilder:
    """Builds T1/T2/T3 context for documents based on taxonomy definitions.

    This class handles the logic of:
    1. Resolving group keys from extracted entities
    2. Finding related documents via link strategies
    3. Preparing LLM prompts for context generation
    4. Structuring context results

    It does NOT call LLMs directly — it produces ContextResult objects
    with populated `input_prompt` fields. The caller is responsible for
    running the LLM and populating `context_summary`.
    """

    def __init__(self, document_store: DocumentStore) -> None:
        self._store = document_store

    def build_t1(self, doc: DocumentRecord, type_def: DocTypeDef,
                 subtype: str | None = None) -> ContextResult:
        """Build T1 (document-level) context.

        T1 is self-contained — no related document lookup needed.
        """
        tier_def = type_def.get_context_tier("t1", subtype)
        if not tier_def:
            return ContextResult(
                tier="t1", scope="document", doc_id=doc.doc_id,
                group_key={"doc_id": doc.doc_id}, related_doc_ids=[],
            )

        # Build prompt with document content + entity values
        prompt = self._build_prompt(tier_def, doc, [])

        return ContextResult(
            tier="t1",
            scope="document",
            doc_id=doc.doc_id,
            group_key={"doc_id": doc.doc_id},
            related_doc_ids=[],
            input_prompt=prompt,
        )

    def build_t2(self, doc: DocumentRecord, type_def: DocTypeDef,
                 subtype: str | None = None) -> ContextResult:
        """Build T2 (cross-document) context.

        Finds related documents using the link strategy and groups them.
        """
        tier_def = type_def.get_context_tier("t2", subtype)
        if not tier_def:
            return ContextResult(
                tier="t2", scope="cross_document", doc_id=doc.doc_id,
                group_key={}, related_doc_ids=[],
            )

        # Resolve group key
        group_key = self._resolve_group_key(tier_def.group_by, doc)

        # Find related documents
        related = self._find_related(doc, tier_def.link_strategy)

        # Build prompt with primary doc + related docs
        prompt = self._build_prompt(tier_def, doc, related)

        return ContextResult(
            tier="t2",
            scope="cross_document",
            doc_id=doc.doc_id,
            group_key=group_key,
            related_doc_ids=[r.doc_id for r in related],
            input_prompt=prompt,
        )

    def build_t3(self, doc: DocumentRecord, type_def: DocTypeDef,
                 subtype: str | None = None) -> ContextResult:
        """Build T3 (entity-level) context.

        Finds all documents related to the primary entity across all types.
        """
        tier_def = type_def.get_context_tier("t3", subtype)
        if not tier_def:
            return ContextResult(
                tier="t3", scope="entity", doc_id=doc.doc_id,
                group_key={}, related_doc_ids=[],
            )

        # Resolve group key
        group_key = self._resolve_group_key(tier_def.group_by, doc)

        # Find related documents (broader search for T3)
        related = self._find_related(doc, tier_def.link_strategy)

        # Build prompt
        prompt = self._build_prompt(tier_def, doc, related)

        return ContextResult(
            tier="t3",
            scope="entity",
            doc_id=doc.doc_id,
            group_key=group_key,
            related_doc_ids=[r.doc_id for r in related],
            input_prompt=prompt,
        )

    def build_all_tiers(self, doc: DocumentRecord, type_def: DocTypeDef,
                        subtype: str | None = None) -> dict[str, ContextResult]:
        """Build all three context tiers for a document."""
        return {
            "t1": self.build_t1(doc, type_def, subtype),
            "t2": self.build_t2(doc, type_def, subtype),
            "t3": self.build_t3(doc, type_def, subtype),
        }

    # ── Internal helpers ─────────────────────────────────────────────

    def _resolve_group_key(self, group_by: list[str], doc: DocumentRecord) -> dict[str, Any]:
        """Extract group key values from a document's entities."""
        key = {}
        for field_name in group_by:
            if field_name == "doc_id":
                key["doc_id"] = doc.doc_id
            elif field_name in doc.entities:
                key[field_name] = doc.entities[field_name]
            elif field_name in doc.metadata:
                key[field_name] = doc.metadata[field_name]
        return key

    def _find_related(self, doc: DocumentRecord,
                      strategy: LinkStrategy | None) -> list[LinkMatch]:
        """Find related documents using a link strategy."""
        if not strategy:
            return []

        # Build match criteria from the document's entities
        match_criteria: dict[str, Any] = {}
        for field_name in strategy.match_fields:
            value = doc.entities.get(field_name) or doc.metadata.get(field_name)
            if value is not None:
                match_criteria[field_name] = value

        if not match_criteria:
            return []

        # Query the document store
        return self._store.find_related(
            exclude_doc_id=doc.doc_id,
            match_criteria=match_criteria,
            match_types=strategy.match_types,
            temporal_window=strategy.temporal_window,
        )

    def _build_prompt(self, tier_def: ContextTierDef, doc: DocumentRecord,
                      related: list[LinkMatch]) -> str:
        """Build an LLM prompt for context generation."""
        parts: list[str] = []

        # System instruction
        parts.append(tier_def.context_prompt)
        parts.append("")

        # Primary document
        parts.append("## Primary Document")
        if doc.classification:
            parts.append(f"Type: {doc.classification.qualified_name}")
        parts.append(f"Source: {doc.source}")

        # Entity values
        if doc.entities:
            parts.append("\n### Extracted Entities")
            for k, v in doc.entities.items():
                if v is not None:
                    parts.append(f"- **{k}**: {v}")

        # Content summary
        if doc.raw_text:
            text_preview = doc.raw_text[:3000]
            parts.append(f"\n### Content\n{text_preview}")
            if len(doc.raw_text) > 3000:
                parts.append(f"... ({len(doc.raw_text) - 3000} more characters)")

        # Related documents
        if related:
            parts.append(f"\n## Related Documents ({len(related)} found)")
            for i, match in enumerate(related[:20]):  # Cap at 20
                rel_doc = self._store.get(match.doc_id)
                if rel_doc:
                    parts.append(f"\n### Related #{i + 1}: {match.qualified_type}")
                    if rel_doc.entities:
                        for k, v in rel_doc.entities.items():
                            if v is not None:
                                parts.append(f"- {k}: {v}")
                    if rel_doc.raw_text:
                        parts.append(f"Content preview: {rel_doc.raw_text[:500]}")

        return "\n".join(parts)


# ── Document store interface ─────────────────────────────────────────────────


class DocumentStore:
    """Abstract interface for the document store.

    Implementations provide storage and retrieval of DocumentRecords.
    The ContextBuilder uses this to find related documents.
    """

    def get(self, doc_id: str) -> DocumentRecord | None:
        """Retrieve a document by ID."""
        raise NotImplementedError

    def find_related(
        self,
        exclude_doc_id: str,
        match_criteria: dict[str, Any],
        match_types: list[str] | None = None,
        temporal_window: str | None = None,
    ) -> list[LinkMatch]:
        """Find documents matching the given criteria.

        Args:
            exclude_doc_id: Exclude this document from results.
            match_criteria: Field name → value pairs to match on.
            match_types: Only search these doc types (qualified names).
            temporal_window: Time window for relevance (e.g., '90d', '1y').

        Returns:
            List of matching documents ordered by relevance.
        """
        raise NotImplementedError

    def store(self, doc: DocumentRecord) -> None:
        """Store or update a document record."""
        raise NotImplementedError

    def list_by_type(self, qualified_type: str, limit: int = 100) -> list[DocumentRecord]:
        """List documents of a given type."""
        raise NotImplementedError


class InMemoryDocumentStore(DocumentStore):
    """Simple in-memory document store for development and testing."""

    def __init__(self) -> None:
        self._docs: dict[str, DocumentRecord] = {}

    def get(self, doc_id: str) -> DocumentRecord | None:
        return self._docs.get(doc_id)

    def store(self, doc: DocumentRecord) -> None:
        self._docs[doc_id := doc.doc_id] = doc

    def list_by_type(self, qualified_type: str, limit: int = 100) -> list[DocumentRecord]:
        results = []
        for doc in self._docs.values():
            if doc.classification and doc.classification.qualified_name.startswith(qualified_type):
                results.append(doc)
                if len(results) >= limit:
                    break
        return results

    def find_related(
        self,
        exclude_doc_id: str,
        match_criteria: dict[str, Any],
        match_types: list[str] | None = None,
        temporal_window: str | None = None,
    ) -> list[LinkMatch]:
        matches: list[LinkMatch] = []
        for doc_id, doc in self._docs.items():
            if doc_id == exclude_doc_id:
                continue

            # Type filter
            if match_types and doc.classification:
                if not any(doc.classification.qualified_name.startswith(t) for t in match_types):
                    continue

            # Field matching — score by number of matching fields
            match_count = 0
            matched_fields: dict[str, Any] = {}
            for field_name, target_value in match_criteria.items():
                doc_value = doc.entities.get(field_name) or doc.metadata.get(field_name)
                if doc_value is not None and self._values_match(doc_value, target_value):
                    match_count += 1
                    matched_fields[field_name] = doc_value

            if match_count > 0:
                matches.append(LinkMatch(
                    doc_id=doc_id,
                    qualified_type=doc.classification.qualified_name if doc.classification else "unknown",
                    match_fields=matched_fields,
                    relevance_score=match_count / len(match_criteria),
                ))

        # Sort by relevance
        matches.sort(key=lambda m: m.relevance_score, reverse=True)
        return matches

    @staticmethod
    def _values_match(a: Any, b: Any) -> bool:
        """Flexible value matching — handles strings, lists, case-insensitive."""
        if isinstance(a, str) and isinstance(b, str):
            return a.lower() == b.lower()
        if isinstance(a, list) and isinstance(b, str):
            return any(str(item).lower() == b.lower() for item in a)
        if isinstance(a, str) and isinstance(b, list):
            return any(a.lower() == str(item).lower() for item in b)
        return a == b
