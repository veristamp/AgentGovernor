"""
Concept Resolver - Canonical Resolution for the Dual-Graph.

Transforms extracted terms into a connected graph:
1. L1 Cache: In-memory lookup
2. L2 Postgres: Exact match on global_concepts
3. L3 Qdrant: Vector similarity for synonyms
4. L4 Create: New concept if not found

Features:
- Dynamic IDF-based noise filtering (concepts in >10% docs = noise)
- Position-aware edge weighting (heading=1.0, first_sent=0.8, freq≥3=0.7, else=0.5)
- Frequency tracking for statistical learning
"""

import asyncio
import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy import text

from config import get_logger

logger = get_logger("concept_resolver")

# Constants
SIMILARITY_THRESHOLD = 0.92
NOISE_THRESHOLD_PERCENT = 0.10
MIN_NOISE_COUNT = 50

try:
    from config import DATABASE_CONFIG
    DEFAULT_COLLECTION = DATABASE_CONFIG.qdrant_collection_concepts
except ImportError:
    DEFAULT_COLLECTION = "concepts"


@dataclass
class ResolvedConcept:
    """A resolved concept with its ID and resolution method."""
    concept_id: int
    original_term: str
    canonical_name: str
    resolution_type: str  # 'cache', 'exact', 'vector', 'new', 'noise'
    doc_count: int = 1
    similarity_score: Optional[float] = None
    is_noise: bool = False


@dataclass
class ConceptEdge:
    """An edge connecting a chunk to a concept."""
    source_id: int
    target_id: int
    edge_type: str = "MENTIONS"
    weight: float = 1.0


def calculate_edge_weight(term: str, chunk_text: str, heading: Optional[str] = None, count: int = 1) -> float:
    """Calculate edge weight based on position and frequency."""
    term_lower = term.lower()
    
    # In heading = definition
    if heading and term_lower in heading.lower():
        return 1.0
    
    # In first sentence = key topic
    match = re.match(r'^[^.!?]*[.!?]', chunk_text)
    if match and term_lower in match.group(0).lower():
        return 0.8
    
    # High frequency = important
    if count >= 3:
        return 0.7
    
    return 0.5


class ConceptResolver:
    """
    Resolves terms to canonical concept IDs with 4-tier lookup.
    
    Handles async/sync Qdrant clients transparently.
    """
    
    def __init__(
        self,
        pg_session=None,
        qdrant_client=None,
        embedding_model=None,
        collection_name: str = DEFAULT_COLLECTION,
        similarity_threshold: float = SIMILARITY_THRESHOLD,
        noise_threshold_percent: float = NOISE_THRESHOLD_PERCENT,
        total_docs: int = 0
    ):
        self.pg_session = pg_session
        self.qdrant_client = qdrant_client
        self.embedding_model = embedding_model
        self.collection_name = collection_name
        self.similarity_threshold = similarity_threshold
        self.noise_threshold_percent = noise_threshold_percent
        self.total_docs = total_docs
        
        self._cache: Dict[str, Tuple[int, int]] = {}  # normalized → (id, doc_count)
        self._aliases: Dict[str, str] = {}  # normalized → canonical_name
        self._noise_cache: Set[str] = set()
        self.stats = defaultdict(int)
    
    def set_total_docs(self, count: int):
        self.total_docs = count
    
    def get_stats(self) -> Dict[str, int]:
        return dict(self.stats)
    
    def clear_cache(self):
        self._cache.clear()
        self._aliases.clear()
        self._noise_cache.clear()
        self.stats.clear()
    
    # =========================================================================
    # HELPERS
    # =========================================================================
    
    def _normalize(self, term: str) -> str:
        return term.strip().lower()
    
    def _noise_threshold(self) -> int:
        if self.total_docs <= 0:
            return MIN_NOISE_COUNT
        return max(int(self.total_docs * self.noise_threshold_percent), MIN_NOISE_COUNT)
    
    def _is_noise(self, doc_count: int) -> bool:
        return doc_count > self._noise_threshold()
    
    def _encode(self, term: str) -> List[float]:
        if not self.embedding_model:
            raise ValueError("No embedding model")
        if hasattr(self.embedding_model, 'encode'):
            return self.embedding_model.encode(term, convert_to_numpy=True).tolist()
        return self.embedding_model(term)
    
    async def _qdrant_call(self, method: str, **kwargs):
        """Universal async/sync Qdrant caller."""
        if not self.qdrant_client:
            return None
        fn = getattr(self.qdrant_client, method, None)
        if not fn:
            return None
        if asyncio.iscoroutinefunction(fn):
            return await fn(**kwargs)
        return fn(**kwargs)
    
    def _make_noise_result(self, term: str, normalized: str, concept_id: int = -1, 
                           doc_count: int = 1, similarity: float = None) -> ResolvedConcept:
        """Create a noise result and update caches."""
        self._noise_cache.add(normalized)
        self.stats['noise_filtered'] += 1
        return ResolvedConcept(
            concept_id=concept_id,
            original_term=term,
            canonical_name=self._aliases.get(normalized, term),
            resolution_type='noise',
            doc_count=doc_count,
            similarity_score=similarity,
            is_noise=True
        )
    
    def _cache_and_return(self, term: str, normalized: str, concept_id: int, 
                          doc_count: int, res_type: str, similarity: float = None) -> ResolvedConcept:
        """Cache result and return ResolvedConcept."""
        self._cache[normalized] = (concept_id, doc_count)
        self._aliases[normalized] = term
        self.stats[f'{res_type}_matches' if res_type != 'new' else 'new_concepts'] += 1
        return ResolvedConcept(
            concept_id=concept_id,
            original_term=term,
            canonical_name=term,
            resolution_type=res_type,
            doc_count=doc_count,
            similarity_score=similarity
        )
    
    # =========================================================================
    # DATABASE OPERATIONS
    # =========================================================================
    
    async def _pg_get(self, name: str) -> Optional[Tuple[int, int]]:
        """L2: Postgres exact match."""
        if not self.pg_session:
            return None
        try:
            result = await self.pg_session.execute(
                text("SELECT id, doc_count FROM global_concepts WHERE LOWER(name) = :name LIMIT 1"),
                {"name": self._normalize(name)}
            )
            row = result.fetchone()
            return (row[0], row[1]) if row else None
        except Exception as e:
            logger.warning(f"PG lookup failed for '{name}': {e}")
            return None
    
    async def _pg_increment(self, concept_id: int) -> int:
        """Increment doc_count."""
        if not self.pg_session:
            return 1
        try:
            result = await self.pg_session.execute(
                text("UPDATE global_concepts SET doc_count = doc_count + 1 WHERE id = :id RETURNING doc_count"),
                {"id": concept_id}
            )
            await self.pg_session.commit()
            row = result.fetchone()
            return row[0] if row else 1
        except Exception as e:
            logger.warning(f"PG increment failed: {e}")
            return 1
    
    async def _pg_create(self, name: str) -> Tuple[int, int]:
        """Create new concept."""
        if not self.pg_session:
            raise ValueError("No PG session")
        result = await self.pg_session.execute(
            text("""
                INSERT INTO global_concepts (name, doc_count) VALUES (:name, 1)
                ON CONFLICT (name) DO UPDATE SET doc_count = global_concepts.doc_count + 1
                RETURNING id, doc_count
            """),
            {"name": name}
        )
        await self.pg_session.commit()
        row = result.fetchone()
        return (row[0], row[1])
    
    async def _qdrant_search(self, term: str) -> Optional[Tuple[int, str, float]]:
        """L3: Vector similarity search."""
        if not self.qdrant_client or not self.embedding_model:
            return None
        try:
            results = await self._qdrant_call(
                'search',
                collection_name=self.collection_name,
                query_vector=self._encode(term),
                limit=1,
                with_payload=True,
                score_threshold=self.similarity_threshold
            )
            if results:
                hit = results[0]
                return (hit.payload.get("concept_id"), hit.payload.get("canonical_name", term), hit.score)
        except Exception as e:
            logger.debug(f"Qdrant search failed: {e}")
        return None
    
    async def _qdrant_upsert(self, concept_id: int, term: str):
        """Add concept to Qdrant for future matching."""
        if not self.qdrant_client or not self.embedding_model:
            return
        try:
            from qdrant_client.models import PointStruct
            await self._qdrant_call(
                'upsert',
                collection_name=self.collection_name,
                points=[PointStruct(
                    id=concept_id,
                    vector=self._encode(term),
                    payload={"concept_id": concept_id, "canonical_name": term}
                )]
            )
        except Exception as e:
            logger.debug(f"Qdrant upsert failed: {e}")
    
    # =========================================================================
    # RESOLUTION
    # =========================================================================
    
    async def resolve_single(self, term: str) -> ResolvedConcept:
        """Resolve a single term through the 4-tier lookup."""
        normalized = self._normalize(term)
        
        # Noise cache check
        if normalized in self._noise_cache:
            return self._make_noise_result(term, normalized)
        
        # L1: Memory cache
        if normalized in self._cache:
            cid, count = self._cache[normalized]
            if self._is_noise(count):
                return self._make_noise_result(term, normalized, cid, count)
            self.stats['cache_hits'] += 1
            return ResolvedConcept(cid, term, self._aliases.get(normalized, term), 'cache', count)
        
        # L2: Postgres exact
        pg = await self._pg_get(term)
        if pg:
            cid, count = pg
            if self._is_noise(count):
                self._cache[normalized] = (cid, count)
                return self._make_noise_result(term, normalized, cid, count)
            new_count = await self._pg_increment(cid)
            return self._cache_and_return(term, normalized, cid, new_count, 'exact')
        
        # L3: Qdrant vector
        vec = await self._qdrant_search(term)
        if vec:
            cid, canonical, similarity = vec
            pg_check = await self._pg_get(canonical)
            count = pg_check[1] if pg_check else 1
            if self._is_noise(count):
                self._cache[normalized] = (cid, count)
                return self._make_noise_result(term, normalized, cid, count, similarity)
            new_count = await self._pg_increment(cid)
            self._cache[normalized] = (cid, new_count)
            self._aliases[normalized] = canonical
            self.stats['vector_merges'] += 1
            logger.info(f"Vector merge: '{term}' → '{canonical}' (sim={similarity:.3f})")
            return ResolvedConcept(cid, term, canonical, 'vector', new_count, similarity)
        
        # L4: Create new
        cid, count = await self._pg_create(term)
        await self._qdrant_upsert(cid, term)
        logger.info(f"New concept: '{term}' (id={cid})")
        return self._cache_and_return(term, normalized, cid, count, 'new')
    
    async def resolve(
        self,
        terms: List[str],
        source_chunk_id: int,
        chunk_text: str = "",
        chunk_heading: Optional[str] = None
    ) -> List[ConceptEdge]:
        """Resolve terms and generate weighted edges."""
        edges = []
        seen: Set[int] = set()
        
        # Count occurrences
        text_lower = chunk_text.lower()
        counts = {t.lower(): text_lower.count(t.lower()) for t in terms if t}
        
        for term in terms:
            if not term or not term.strip():
                continue
            
            try:
                resolved = await self.resolve_single(term)
                
                if resolved.concept_id in seen:
                    continue
                seen.add(resolved.concept_id)
                
                if resolved.is_noise:
                    # Demote noise: low weight, different edge type
                    edges.append(ConceptEdge(source_chunk_id, resolved.concept_id, "BELONGS_TO_DOMAIN", 0.1))
                else:
                    weight = calculate_edge_weight(term, chunk_text, chunk_heading, counts.get(term.lower(), 1))
                    edges.append(ConceptEdge(source_chunk_id, resolved.concept_id, "MENTIONS", weight))
            except Exception as e:
                logger.error(f"Failed to resolve '{term}': {e}")
        
        return edges
    
    async def batch_resolve(self, chunks: List[Dict[str, Any]], term_key: str = "concepts") -> List[ConceptEdge]:
        """Batch resolve concepts from multiple chunks."""
        all_edges = []
        for chunk in chunks:
            cid = chunk.get("id")
            terms = chunk.get(term_key, [])
            if cid and terms:
                edges = await self.resolve(
                    terms, cid, 
                    chunk.get("text", ""),
                    chunk.get("heading") or chunk.get("section_path", "").split(" > ")[-1]
                )
                all_edges.extend(edges)
        return all_edges
