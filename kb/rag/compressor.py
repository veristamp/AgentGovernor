# rag/compressor.py
"""
Semantic Context Compressor - Async sentence-level compression.

Keeps only query-relevant sentences while preserving code blocks.
Uses the same embedding infrastructure as the rest of RAG.
"""

import re
import asyncio

from typing import List, Dict, Any, Optional, Tuple
import numpy as np
from config import get_logger

logger = get_logger("Compressor")

# Optimized regex for sentence splitting
SENTENCE_SPLIT_RE = re.compile(r'(?<!\w\.\w.)(?<![A-Z][a-z]\.)(?<=\.|\?|\!)\s')
CODE_FENCE_RE = re.compile(r'```[\s\S]*?```', re.MULTILINE)

class SemanticCompressor:
    """
    Async Semantic Compressor - keeps only query-relevant sentences.
    
    Architecture:
    - Reuses DenseEmbedder for embeddings (no separate model loading)
    - Fully async (compatible with RAG pipeline)
    - Preserves code blocks intact
    
    Usage:
        compressor = SemanticCompressor(dense_embedder)
        compressed = await compressor.compress_chunks(query, chunks)
    """
    
    def __init__(
        self, 
        dense_embedder,
        threshold: float = 0.35,
        window_size: int = 1
    ):
        """
        Args:
            dense_embedder: DenseEmbedder instance (shared with RAG)
            threshold: Min cosine similarity to keep sentence (def: 0.35)
            window_size: Sentences to keep around relevant ones (def: 1)
        """
        self.embedder = dense_embedder
        self.threshold = threshold
        self.window_size = window_size
        logger.info(f"✅ SemanticCompressor Ready (threshold={threshold})")
    
    async def compress_chunks(
        self, 
        query: str, 
        chunks: List[Dict[str, Any]],
        min_keep_chars: int = 300
    ) -> List[Dict[str, Any]]:
        """
        Compress chunks by keeping only query-relevant sentences.
        
        Args:
            query: The user's search query
            chunks: List of chunk dicts (with 'text' or 'content' field)
            min_keep_chars: Below this char count, keep entire chunk
            
        Returns:
            List of compressed chunk dicts
        """
        if not chunks:
            return []
        
        # Get query embedding
        query_embs = await self.embedder.encode([query])
        query_vec = np.array(query_embs[0])
        
        compressed = []
        
        # Process chunks concurrently
        tasks = [
            self._compress_single(chunk, query_vec, min_keep_chars)
            for chunk in chunks
        ]
        results = await asyncio.gather(*tasks)
        
        return [c for c in results if c is not None]
    
    async def _compress_single(
        self, 
        chunk: Dict[str, Any], 
        query_vec: np.ndarray,
        min_keep_chars: int
    ) -> Optional[Dict[str, Any]]:
        """Compress a single chunk."""
        text = chunk.get("content") or chunk.get("text", "")
        chunk_type = chunk.get("type", "").upper()
        
        # Skip code blocks - always keep intact
        if chunk_type == "CODE" or "```" in text[:100]:
            return chunk
        
        # Small chunks - keep as is
        if len(text) < min_keep_chars:
            return chunk
        
        # Protect code fences from sentence splitting
        code_blocks, protected_text = self._protect_code_fences(text)
        
        # Split into sentences
        sentences = [s.strip() for s in SENTENCE_SPLIT_RE.split(protected_text) if s.strip()]
        if not sentences or len(sentences) <= 2:
            return chunk  # Too few sentences to compress
        
        # Get sentence embeddings
        try:
            sent_embs = await self.embedder.encode(sentences)
            sent_vecs = np.array(sent_embs)
        except Exception as e:
            logger.warning(f"Embedding failed: {e}")
            return chunk
        
        # Calculate cosine similarities
        similarities = self._cosine_sim(query_vec, sent_vecs)
        
        # Find relevant sentences + window
        keep_indices = set()
        for i, score in enumerate(similarities):
            if score >= self.threshold:
                start = max(0, i - self.window_size)
                end = min(len(sentences), i + self.window_size + 1)
                keep_indices.update(range(start, end))
        
        # If nothing relevant, check if we should drop or keep
        if not keep_indices:
            # Keep first sentence as minimal context
            if len(text) < min_keep_chars * 2:
                return chunk
            return None  # Drop low-relevance chunk
        
        # Reconstruct compressed text
        kept_sentences = [sentences[i] for i in sorted(keep_indices)]
        compressed_text = " ".join(kept_sentences)
        
        # Restore code blocks
        compressed_text = self._restore_code_fences(compressed_text, code_blocks)
        
        # Create new chunk
        new_chunk = dict(chunk)
        new_chunk["text"] = compressed_text
        if "content" in new_chunk:
            new_chunk["content"] = compressed_text
        new_chunk["compressed"] = True
        new_chunk["original_length"] = len(text)
        new_chunk["compressed_length"] = len(compressed_text)
        
        return new_chunk
    
    def _protect_code_fences(self, text: str) -> Tuple[Dict[str, str], str]:
        """Replace code fences with placeholders."""
        code_blocks = {}
        for i, block in enumerate(CODE_FENCE_RE.findall(text)):
            key = f"__CODE_{i}__"
            code_blocks[key] = block
            text = text.replace(block, key, 1)
        return code_blocks, text
    
    def _restore_code_fences(self, text: str, code_blocks: Dict[str, str]) -> str:
        """Restore code fences from placeholders."""
        for key, val in code_blocks.items():
            text = text.replace(key, val)
        return text
    
    def _cosine_sim(self, query_vec: np.ndarray, sent_vecs: np.ndarray) -> np.ndarray:
        """Calculate cosine similarity between query and sentences."""
        # Normalize vectors
        query_norm = query_vec / (np.linalg.norm(query_vec) + 1e-8)
        sent_norms = sent_vecs / (np.linalg.norm(sent_vecs, axis=1, keepdims=True) + 1e-8)
        
        # Dot product = cosine similarity for normalized vectors
        return np.dot(sent_norms, query_norm)

async def create_compressor(dense_embedder=None, **kwargs) -> SemanticCompressor:
    """
    Factory function to create a SemanticCompressor.
    
    If no embedder provided, creates one using EMBEDDING_CONFIG.
    """
    if dense_embedder is None:
        from .models import DenseEmbedder
        dense_embedder = DenseEmbedder()
    
    return SemanticCompressor(dense_embedder, **kwargs)
