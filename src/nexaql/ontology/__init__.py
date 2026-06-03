"""NexaQL ontology package — models, loader, and prompt generation."""

from .loader import invalidate_cache, load_ontology
from .models import (
    DatasourceConfig,
    FieldDef,
    JoinStep,
    Ontology,
    OntologyEdge,
    OntologyNode,
    SpecialFilter,
)
from .prompt import ontology_summary, ontology_to_agent_prompt, ontology_to_prompt_text

__all__ = [
    "DatasourceConfig",
    "FieldDef",
    "JoinStep",
    "Ontology",
    "OntologyEdge",
    "OntologyNode",
    "SpecialFilter",
    "invalidate_cache",
    "load_ontology",
    "ontology_summary",
    "ontology_to_agent_prompt",
    "ontology_to_prompt_text",
]
