# rag/models.py
"""
High-performance embedding and reranking models.
Supports local (FastEmbed/SentenceTransformers) and remote (Ollama/OpenAI/Infinity) providers.

Architecture:
- Async First: All models use 'async def' to ensure non-blocking I/O for remote providers.
- Stateless Ready: Remote providers make the RAG application process purely logical and lightweight.
- Thread-Safe Local: Local models are executed in thread pools to avoid blocking the event loop.
"""

import os
import asyncio
from typing import List, Dict, Any, Sequence, Optional, Union
import httpx
import onnxruntime as ort
from fastembed import TextEmbedding, SparseTextEmbedding
from sentence_transformers.cross_encoder import CrossEncoder

# Import central config
from config.embeddings import EMBEDDING_CONFIG
from config import get_logger

logger = get_logger("RAGModels")

# Global singleton cache for local models to prevent re-loading heavy weights
_MODEL_CACHE: Dict[str, Any] = {}

class DenseEmbedder:
    """Unified Dense Embedder Facade (Async)."""
    
    def __init__(self, model_name: str = None, provider: str = None, base_url: str = None, batch_size: int = 16):
        self.model_name = model_name or EMBEDDING_CONFIG.model_name
        self.provider = provider or EMBEDDING_CONFIG.provider
        self.base_url = base_url or EMBEDDING_CONFIG.base_url
        self.batch_size = batch_size
        
        self.impl = self._get_implementation()
        self.dim = EMBEDDING_CONFIG.dim # Default, will be updated if probe succeeds

    def _get_implementation(self):
        if self.provider == "ollama":
            return OllamaEmbedder(self.model_name, self.base_url)
        elif self.provider in ["openai", "infinity", "vllm"]:
            return OpenAIEmbedder(self.model_name, self.base_url)
        else:
            return FastEmbedEmbedder(self.model_name, self.batch_size)

    async def encode(self, texts: Sequence[str]) -> List[List[float]]:
        """Return list of vectors (Async)."""
        return await self.impl.encode(texts)

class FastEmbedEmbedder:
    """Local FastEmbed-powered Dense Embedder (Threaded Async)."""
    def __init__(self, model_name: str, batch_size: int):
        avail = list(ort.get_available_providers())
        providers = []
        if "DmlExecutionProvider" in avail:
            providers.append("DmlExecutionProvider")
        if "CUDAExecutionProvider" in avail:
            providers.append("CUDAExecutionProvider")
        providers.append("CPUExecutionProvider")

            
        if model_name in _MODEL_CACHE:
            self.model = _MODEL_CACHE[model_name]
            return

        logger.info(f"🚀 Loading Local Dense Embedder: {model_name} (Providers: {providers})")
        try:
            self.model = TextEmbedding(model_name=model_name, batch_size=batch_size, providers=providers)
        except Exception:
            self.model = TextEmbedding(model_name=model_name, batch_size=batch_size, providers=["CPUExecutionProvider"])
        
        _MODEL_CACHE[model_name] = self.model

    async def encode(self, texts: Sequence[str]) -> List[List[float]]:
        # FastEmbed is a sync generator, we run in thread to keep loop free
        return await asyncio.to_thread(self._sync_encode, texts)

    def _sync_encode(self, texts: Sequence[str]) -> List[List[float]]:
        return [v.tolist() for v in self.model.embed(list(texts))]

class OllamaEmbedder:
    """Remote Ollama-powered Dense Embedder (True Async)."""
    def __init__(self, model_name: str, base_url: str = None):
        self.model_name = model_name
        self.base_url = (base_url or "http://localhost:11434").rstrip("/")
        logger.info(f"🌐 Using Remote Ollama Embedder: {model_name} @ {self.base_url}")

    async def encode(self, texts: Sequence[str]) -> List[List[float]]:
        async with httpx.AsyncClient(timeout=60.0) as client:
            embeddings = []
            for text in texts:
                response = await client.post(
                    f"{self.base_url}/api/embeddings",
                    json={"model": self.model_name, "prompt": text}
                )
                response.raise_for_status()
                embeddings.append(response.json()["embedding"])
            return embeddings

class OpenAIEmbedder:
    """Remote OpenAI-compatible Dense Embedder (True Async)."""
    def __init__(self, model_name: str, base_url: str = None):
        self.model_name = model_name
        self.base_url = (base_url or "https://api.openai.com/v1").rstrip("/")
        self.api_key = os.getenv("OPENAI_API_KEY") if "openai" in self.base_url else "no-key"
        logger.info(f"🌐 Using Remote API Embedder: {model_name} @ {self.base_url}")

    async def encode(self, texts: Sequence[str]) -> List[List[float]]:
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self.base_url}/embeddings",
                json={"model": self.model_name, "input": list(texts)},
                headers=headers
            )
            response.raise_for_status()
            data = response.json()
            # Sort by index to maintain order
            sorted_data = sorted(data["data"], key=lambda x: x["index"])
            return [item["embedding"] for item in sorted_data]

class SparseEmbedder:
    """FastEmbed-powered BM25 Sparse Embedder (Threaded Async)."""
    
    def __init__(self, model_name: str = None):
        model_name = model_name or EMBEDDING_CONFIG.sparse_model
        if model_name in _MODEL_CACHE:
            self.model = _MODEL_CACHE[model_name]
            return

        logger.info(f"🚀 Loading Sparse Embedder: {model_name}")
        self.model = SparseTextEmbedding(model_name=model_name)
        _MODEL_CACHE[model_name] = self.model

    async def encode(self, texts: Sequence[str]) -> List[Dict[str, Any]]:
        return await asyncio.to_thread(self._sync_encode, texts)

    def _sync_encode(self, texts: Sequence[str]) -> List[Dict[str, Any]]:
        out = []
        for obj in self.model.embed(texts):
            indices = getattr(obj, "indices", [])
            values = getattr(obj, "values", [])
            out.append({
                "indices": [int(i) for i in indices],
                "values": [float(v) for v in values]
            })
        return out

class Reranker:
    """Unified Reranker Facade (Async)."""
    
    def __init__(self, model_name: str = None, provider: str = None, base_url: str = None):
        self.model_name = model_name or EMBEDDING_CONFIG.reranker_model
        self.provider = provider or EMBEDDING_CONFIG.reranker_provider
        self.base_url = base_url or EMBEDDING_CONFIG.reranker_base_url
        
        if self.provider == "local":
            self.impl = LocalReranker(self.model_name)
        else:
            # remote, cohere, infinity, etc.
            self.impl = RemoteReranker(self.model_name, self.base_url)

    async def rerank(self, query: str, chunks: List[Dict[str, Any]], top_k: int = 5) -> List[Dict[str, Any]]:
        if not chunks: return []
        return await self.impl.rerank(query, chunks, top_k)

class LocalReranker:
    """Local Cross-Encoder Reranker (Threaded Async)."""
    def __init__(self, model_name: str):
        if model_name in _MODEL_CACHE:
            self.model = _MODEL_CACHE[model_name]
            return

        logger.info(f"🚀 Loading Local Reranker: {model_name}")
        try:
            self.model = CrossEncoder(model_name)
            _MODEL_CACHE[model_name] = self.model
        except Exception as e:
            logger.error(f"❌ Failed to load Reranker: {e}")
            self.model = None

    async def rerank(self, query: str, chunks: List[Dict[str, Any]], top_k: int) -> List[Dict[str, Any]]:
        if not self.model: return chunks[:top_k]
        return await asyncio.to_thread(self._sync_rerank, query, chunks, top_k)

    def _sync_rerank(self, query: str, chunks: List[Dict[str, Any]], top_k: int) -> List[Dict[str, Any]]:
        pairs = [[query, c.get("text", c.get("content", ""))] for c in chunks]
        scores = self.model.predict(pairs, batch_size=32, show_progress_bar=False)
        
        for i, score in enumerate(scores):
            chunks[i]["rerank_score"] = float(score)
            
        chunks.sort(key=lambda x: x["rerank_score"], reverse=True)
        return chunks[:top_k]

class RemoteReranker:
    """Remote Cross-Encoder Reranker (True Async)."""
    def __init__(self, model_name: str, base_url: str):
        self.model_name = model_name
        self.base_url = (base_url or "").rstrip("/")
        if not self.base_url:
            logger.warning("⚠️ Remote Reranker initialized without base_url!")
        logger.info(f"🌐 Using Remote Reranker @ {self.base_url}")

    async def rerank(self, query: str, chunks: List[Dict[str, Any]], top_k: int) -> List[Dict[str, Any]]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(
                    f"{self.base_url}/rerank",
                    json={
                        "query": query,
                        "documents": [c.get("text", c.get("content", "")) for c in chunks],
                        "top_n": top_k,
                        "model": self.model_name
                    }
                )
                response.raise_for_status()
                results = response.json()["results"]
                
                reranked = []
                for res in results:
                    idx = res["index"]
                    chunk = chunks[idx]
                    chunk["rerank_score"] = res["relevance_score"]
                    reranked.append(chunk)
                return reranked
            except Exception as e:
                logger.error(f"🌐 Remote rerank failed: {e}")
                return chunks[:top_k]
