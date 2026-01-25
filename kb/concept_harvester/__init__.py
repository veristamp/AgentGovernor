"""
Concept Harvester - Semantic Extraction Layer

Provides polymorphic extraction (GLiNER + AST) and canonical concept resolution
for the Dual-Graph architecture.

Architecture:
                    ┌─────────────────────────────────────┐
                    │         ConceptManager              │
                    │   (Orchestrates Ghost Input Flow)   │
                    └─────────────────────────────────────┘
                        ↓              ↓              ↓
              ┌─────────────┐  ┌──────────────┐  ┌──────────────┐
              │ ContextInj. │  │  Harvester   │  │   Resolver   │
              │ (Enrich)    │  │  (Extract)   │  │ (Canonicalize)
              └─────────────┘  └──────────────┘  └──────────────┘

Core Components:
1. ConceptHarvester: Extracts concepts from text, code, and tables.
2. ConceptResolver: Canonicalizes terms and creates weighted graph edges.
3. ContextInjector: Enriches text with structural context (Ghost Input Pattern).
4. ConceptManager: Unified facade that orchestrates the above three.
"""

from .config import HarvesterConfig
from .harvester import ConceptHarvester, Harvester, clean_concept_name
from .concept_resolver import ConceptResolver, ResolvedConcept, ConceptEdge
from .context_injector import ContextInjector, InjectionConfig, inject_context
from .manager import ConceptManager, create_concept_manager, HarvestResult, HarvestStats

__version__ = "3.4.0"
__all__ = [
    # Configuration
    "HarvesterConfig",
    "InjectionConfig",
    
    # Core Components
    "ConceptHarvester",
    "Harvester",  # Backward compat alias
    "ConceptResolver",
    "ContextInjector",
    
    # Orchestrator
    "ConceptManager",
    "create_concept_manager",
    
    # Data Classes
    "ResolvedConcept",
    "ConceptEdge",
    "HarvestResult",
    "HarvestStats",
    
    # Utilities
    "clean_concept_name",
    "inject_context",
]

