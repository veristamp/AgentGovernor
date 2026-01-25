# judgment/linter.py
"""
Semantic Linter - Detects duplicate logic using Hybrid Vector Search.

Uses the same Dense+Sparse (BM25) hybrid search as the RAG pipeline,
but optimized for finding near-identical code blocks.

Features:
- Hybrid search (dense + BM25 sparse)
- Code-only filtering (optionally search only code chunks)
- Group-by-file deduplication
- Configurable similarity threshold
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from pathlib import Path
import asyncio

from config import get_logger, DATABASE_CONFIG, ChunkKeys as K

logger = get_logger("SemanticLinter")


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class DuplicateMatch:
    """A single duplicate match found."""
    score: float
    source: str
    start_line: int
    end_line: int
    text: str
    chunk_type: str = "unknown"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "score": round(self.score, 3),
            "source": self.source,
            "lines": (self.start_line, self.end_line),
            "type": self.chunk_type,
            "text": self.text[:200] + "..." if len(self.text) > 200 else self.text
        }


@dataclass
class LintResult:
    """Result of semantic linting."""
    has_duplicates: bool = False
    duplicate_count: int = 0
    high_similarity_count: int = 0  # >0.95 similarity
    duplicates: List[Dict[str, Any]] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "has_duplicates": self.has_duplicates,
            "duplicate_count": self.duplicate_count,
            "high_similarity": self.high_similarity_count,
            "duplicates": self.duplicates
        }


# =============================================================================
# SEMANTIC LINTER (Hybrid Search)
# =============================================================================

class SemanticLinter:
    """
    Checks for semantic duplication using hybrid vector search.
    
    Shares embedders with RAG pipeline but has custom search logic
    for duplicate detection (higher threshold, exclude self, etc.)
    """
    
    def __init__(
        self, 
        qdrant_client: Optional[Any] = None,
        dense_embedder: Optional[Any] = None,
        sparse_embedder: Optional[Any] = None,
        collection: Optional[str] = None
    ):
        """
        Initialize the linter.
        
        Args:
            qdrant_client: Pre-configured Qdrant client
            dense_embedder: DenseEmbedder instance (shared with RAG)
            sparse_embedder: SparseEmbedder instance (shared with RAG)
            collection: Qdrant collection name
        """
        self._qdrant = qdrant_client
        self._dense = dense_embedder
        self._sparse = sparse_embedder
        self._collection = collection or DATABASE_CONFIG.qdrant_collection_chunks
        self._chunker = None
        
    async def _get_client(self):
        """Lazy-load Qdrant client."""
        if self._qdrant is None:
            from qdrant_client import AsyncQdrantClient
            self._qdrant = AsyncQdrantClient(url=DATABASE_CONFIG.qdrant_url)
        return self._qdrant
    
    def _get_dense(self):
        """Lazy-load dense embedder."""
        if self._dense is None:
            from rag.models import DenseEmbedder
            self._dense = DenseEmbedder()
        return self._dense
    
    def _get_sparse(self):
        """Lazy-load sparse embedder."""
        if self._sparse is None:
            from rag.models import SparseEmbedder
            self._sparse = SparseEmbedder()
        return self._sparse

    def _get_chunker(self):
        """Lazy-load chunker."""
        if self._chunker is None:
            from chunker import create_chunker
            self._chunker = create_chunker()
        return self._chunker

    async def analyze_text(
        self, 
        text: str, 
        filename: str = "snippet.py",
        threshold: float = 0.85,
        limit: int = 3,
        code_only: bool = False,
        use_hybrid: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Analyze text for semantic duplicates using hybrid search.
        
        Args:
            text: Text/code to check
            filename: Name of the file (excluded from results)
            threshold: Minimum similarity score (0-1)
            limit: Max matches per chunk
            code_only: Only search code chunks (not text/tables)
            use_hybrid: Use BM25+Dense hybrid (True) or dense only (False)
            
        Returns:
            List of duplicate findings
        """
        from qdrant_client.http import models as qm
        
        client = await self._get_client()
        dense = self._get_dense()
        sparse = self._get_sparse() if use_hybrid else None
        
        # Chunk the text
        chunker = self._get_chunker()
        result = chunker.process_content(text, filename)
        
        # Select chunks to check
        if code_only:
            chunks_to_check = result.code
        else:
            chunks_to_check = result.text + result.code + result.table
        
        all_duplicates = []
        
        for chunk in chunks_to_check:
            chunk_text = chunk[K.TEXT]
            
            # Skip small fragments
            if len(chunk_text.strip()) < 50:
                continue
            
            # Build filter (exclude current file)
            must_not = [
                qm.FieldCondition(
                    key=K.SOURCE_NAME,
                    match=qm.MatchValue(value=filename)
                )
            ]
            
            # Optional: filter to code chunks only
            must = []
            if code_only:
                must.append(
                    qm.FieldCondition(
                        key=K.TYPE,
                        match=qm.MatchValue(value="code")
                    )
                )
            
            search_filter = qm.Filter(must=must, must_not=must_not) if must else qm.Filter(must_not=must_not)
            
            # Embed (dense + sparse in parallel)
            if use_hybrid and sparse:
                dense_task = dense.encode([chunk_text])
                sparse_task = sparse.encode([chunk_text])
                dense_vecs, sparse_vecs = await asyncio.gather(dense_task, sparse_task)
                
                dense_vec = dense_vecs[0]
                sparse_dict = sparse_vecs[0]
                sparse_vec = qm.SparseVector(
                    indices=sparse_dict["indices"],
                    values=sparse_dict["values"]
                )
                
                # Hybrid search with RRF fusion
                try:
                    prefetch = [
                        qm.Prefetch(
                            query=dense_vec,
                            using="dense",
                            filter=search_filter,
                            limit=limit * 2
                        ),
                        qm.Prefetch(
                            query=sparse_vec,
                            using="bm25",
                            filter=search_filter,
                            limit=limit * 2
                        )
                    ]
                    
                    response = await client.query_points(
                        collection_name=self._collection,
                        prefetch=prefetch,
                        query=qm.FusionQuery(fusion=qm.Fusion.RRF),
                        limit=limit,
                        score_threshold=threshold,
                        with_payload=True
                    )
                    matches = response.points
                    
                except Exception as e:
                    logger.warning(f"Hybrid search failed, falling back to dense: {e}")
                    # Fallback to dense-only
                    response = await client.query_points(
                        collection_name=self._collection,
                        query=dense_vec,
                        using="dense",
                        query_filter=search_filter,
                        limit=limit,
                        score_threshold=threshold,
                        with_payload=True
                    )
                    matches = response.points
            else:
                # Dense-only search
                dense_vecs = await dense.encode([chunk_text])
                dense_vec = dense_vecs[0]
                
                response = await client.query_points(
                    collection_name=self._collection,
                    query=dense_vec,
                    using="dense",
                    query_filter=search_filter,
                    limit=limit,
                    score_threshold=threshold,
                    with_payload=True
                )
                matches = response.points
            
            if matches:
                all_duplicates.append({
                    "chunk": {
                        "text": chunk_text[:200],
                        "type": chunk.get(K.TYPE, "unknown"),
                        "lines": (chunk.get(K.LINE_START), chunk.get(K.LINE_END))
                    },
                    "matches": [
                        DuplicateMatch(
                            score=m.score,
                            source=m.payload.get(K.SOURCE_NAME, ""),
                            start_line=m.payload.get(K.LINE_START, 0),
                            end_line=m.payload.get(K.LINE_END, 0),
                            text=m.payload.get(K.TEXT, "")[:200],
                            chunk_type=m.payload.get(K.TYPE, "unknown")
                        ).to_dict()
                        for m in matches
                    ]
                })
                
        return all_duplicates

    async def analyze_file(
        self, 
        file_path: str,
        threshold: float = 0.85,
        code_only: bool = False
    ) -> List[Dict[str, Any]]:
        """Analyze an entire file for semantic duplication."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
            
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
            
        return await self.analyze_text(
            content, 
            path.name, 
            threshold=threshold,
            code_only=code_only
        )

    async def lint(
        self,
        text: str,
        filename: str = "snippet.py",
        threshold: float = 0.85,
        code_only: bool = False
    ) -> LintResult:
        """
        Run semantic linting and return structured result.
        
        Args:
            text: Text/code to check
            filename: Name of the file
            threshold: Minimum similarity score
            code_only: Only check code blocks
            
        Returns:
            LintResult with findings
        """
        duplicates = await self.analyze_text(
            text, 
            filename, 
            threshold=threshold,
            code_only=code_only
        )
        
        high_sim_count = sum(
            1 for d in duplicates 
            for m in d.get("matches", []) 
            if m.get("score", 0) > 0.95
        )
        
        return LintResult(
            has_duplicates=len(duplicates) > 0,
            duplicate_count=len(duplicates),
            high_similarity_count=high_sim_count,
            duplicates=duplicates
        )


# =============================================================================
# FACTORY
# =============================================================================

def create_linter(
    qdrant_client: Optional[Any] = None,
    dense_embedder: Optional[Any] = None,
    sparse_embedder: Optional[Any] = None,
    collection: Optional[str] = None
) -> SemanticLinter:
    """
    Create a SemanticLinter instance.
    
    For best performance, share embedders with RAG pipeline:
    
        from rag.models import DenseEmbedder, SparseEmbedder
        
        dense = DenseEmbedder()
        sparse = SparseEmbedder()
        
        linter = create_linter(
            qdrant_client=qdrant,
            dense_embedder=dense,
            sparse_embedder=sparse
        )
    """
    return SemanticLinter(
        qdrant_client=qdrant_client,
        dense_embedder=dense_embedder,
        sparse_embedder=sparse_embedder,
        collection=collection
    )
