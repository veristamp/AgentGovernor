# concept_harvester/manager.py
"""
Unified Concept Manager - Orchestrator for the Semantic Graph.

Combines extraction, context injection, and resolution into a single interface.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .concept_resolver import ConceptEdge, ConceptResolver
from .config import HarvesterConfig
from .context_injector import ContextInjector, InjectionConfig
from .harvester import ConceptHarvester
from config import get_logger

logger = get_logger("ConceptManager")


@dataclass
class HarvestStats:
    """Statistics for a harvesting operation."""
    chunks_processed: int = 0
    concepts_extracted: int = 0
    concepts_resolved: int = 0
    concepts_new: int = 0
    concepts_synonyms: int = 0
    concepts_noise: int = 0
    
    def add(self, other: 'HarvestStats'):
        for attr in ('chunks_processed', 'concepts_extracted', 'concepts_resolved',
                     'concepts_new', 'concepts_synonyms', 'concepts_noise'):
            setattr(self, attr, getattr(self, attr) + getattr(other, attr))


@dataclass
class HarvestResult:
    """Result of a harvesting operation."""
    edges: Dict[int, List[ConceptEdge]] = field(default_factory=dict)
    stats: HarvestStats = field(default_factory=HarvestStats)


class ConceptManager:
    """
    Unified manager for concept extraction and resolution.
    
    Orchestrates the Ghost Input pattern:
    1. Inject context (transient)
    2. Extract concepts
    3. Post-process and disambiguate
    4. Resolve to canonical IDs
    """
    
    def __init__(
        self,
        harvester: Optional[ConceptHarvester] = None,
        resolver: Optional[ConceptResolver] = None,
        injector: Optional[ContextInjector] = None,
        config: Optional[HarvesterConfig] = None,
    ):
        self.harvester = harvester or ConceptHarvester(config)
        self.resolver = resolver or ConceptResolver()
        self.injector = injector or ContextInjector()
        self.config = config or self.harvester.config
    
    @property
    def pg_session(self):
        return self.resolver.pg_session
    
    @pg_session.setter
    def pg_session(self, value):
        self.resolver.pg_session = value
    
    # =========================================================================
    # EXTRACTION
    # =========================================================================
    
    def tag_chunk(
        self, 
        chunk: Dict[str, Any], 
        root_topic: Optional[str] = None,
        disambiguate_noise: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Extract concepts from a chunk with Ghost Input pattern.
        
        1. Inject context prefix (transient, never stored)
        2. Run polymorphic extraction
        3. Post-process: disambiguate noise, filter artifacts
        """
        # Inject context and get enriched chunk
        enriched = self.injector.inject_chunk(chunk, root_topic)
        ghost_text = enriched.get("enriched_text", "")
        
        if not ghost_text:
            return []
        
        # Extract from ghost text
        ghost_chunk = {**chunk, "text": ghost_text}
        raw_concepts = self.harvester.extract(ghost_chunk)
        
        if not raw_concepts:
            return []
        
        # Post-process
        effective_root = root_topic or self.injector._resolve_root_topic(
            None, chunk.get("section_path"), chunk.get("source", "")
        )
        
        processed = []
        for concept in raw_concepts:
            name = concept.get("name", "")
            
            # Skip context artifacts
            if name.startswith("[CONTEXT") or name.startswith("CONTEXT:"):
                continue
            
            # Disambiguate noise terms
            if disambiguate_noise and self.injector.is_noise_candidate(name):
                new_name = self.injector.disambiguate_term(name, chunk.get("section_path"), effective_root)
                if new_name != name:
                    concept["original_name"] = name
                    concept["name"] = new_name
                    concept["disambiguated"] = True
            
            # Attach provenance
            concept["source_chunk_id"] = chunk.get("id")
            concept["source_section"] = chunk.get("section_path")
            processed.append(concept)
        
        return processed
    
    # =========================================================================
    # RESOLUTION
    # =========================================================================
    
    async def harvest_chunk(
        self, 
        chunk: Dict[str, Any], 
        root_topic: Optional[str] = None
    ) -> List[ConceptEdge]:
        """Extract and resolve concepts to weighted graph edges."""
        concepts = self.tag_chunk(chunk, root_topic)
        if not concepts:
            return []
        
        chunk_id = chunk.get("id")
        if not chunk_id:
            logger.warning("Chunk missing ID, skipping resolution")
            return []
        
        return await self.resolver.resolve(
            terms=[c["name"] for c in concepts if c.get("name")],
            source_chunk_id=chunk_id,
            chunk_text=chunk.get("text") or chunk.get("original_text", ""),
            chunk_heading=chunk.get("heading") or chunk.get("section_path", "").split(" > ")[-1]
        )
    
    async def harvest_batch(
        self, 
        chunks: List[Dict[str, Any]], 
        root_topic: Optional[str] = None
    ) -> HarvestResult:
        """Process a batch of chunks for the dual-graph."""
        result = HarvestResult()
        result.stats.chunks_processed = len(chunks)
        
        self.resolver.set_total_docs(len(chunks))
        
        for chunk in chunks:
            edges = await self.harvest_chunk(chunk, root_topic)
            if edges:
                result.edges[chunk.get("id")] = edges
                result.stats.concepts_extracted += len(edges)
        
        # Fill stats from resolver
        stats = self.resolver.get_stats()
        result.stats.concepts_resolved = stats.get('exact_matches', 0) + stats.get('vector_merges', 0)
        result.stats.concepts_synonyms = stats.get('vector_merges', 0)
        result.stats.concepts_new = stats.get('new_concepts', 0)
        result.stats.concepts_noise = stats.get('noise_filtered', 0)
        
        return result
    
    # =========================================================================
    # MAINTENANCE
    # =========================================================================
    
    async def garden(self, threshold: float = 0.92):
        """Run graph maintenance (synonym merging, pruning, demotion)."""
        from .graph_gardener import DatabaseGardener
        
        gardener = DatabaseGardener(
            pg_session=self.resolver.pg_session,
            qdrant_client=self.resolver.qdrant_client,
            synonym_threshold=threshold
        )
        return await gardener.run()


def create_concept_manager(
    pg_session=None,
    qdrant_client=None,
    embedding_model=None,
    harvester_config: Optional[HarvesterConfig] = None,
    injection_config: Optional[InjectionConfig] = None
) -> ConceptManager:
    """Factory function for ConceptManager."""
    from config.embeddings import EMBEDDING_CONFIG
    
    config = harvester_config or HarvesterConfig()
    
    return ConceptManager(
        harvester=ConceptHarvester(config),
        resolver=ConceptResolver(
            pg_session=pg_session,
            qdrant_client=qdrant_client,
            embedding_model=embedding_model or EMBEDDING_CONFIG.model_name
        ),
        injector=ContextInjector(injection_config)
    )
