#!/usr/bin/env python3
"""
Shared module for embedding models.
Extracted from upsert.py to be used by both ingestion and retrieval.
"""
from __future__ import annotations

import onnxruntime as ort
from fastembed import TextEmbedding, SparseTextEmbedding
from typing import Sequence, List, Dict, Any

class Embedder:
    """Dense embedding model wrapper."""
    def __init__(self, model_name: str, batch_size: int = 16, use_gpu: bool = True):
        avail = list(ort.get_available_providers())
        # Choose providers: CUDA > DirectML > CPU
        if use_gpu and "CUDAExecutionProvider" in avail:
            providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
        elif use_gpu and "DmlExecutionProvider" in avail:
            providers = ["DmlExecutionProvider", "CPUExecutionProvider"]
        else:
            providers = ["CPUExecutionProvider"]

        print(f"[Embedder] ORT available={avail} | using={providers}")
        try:
            self.model = TextEmbedding(model_name=model_name, batch_size=batch_size, providers=providers)
        except Exception as e:
            print(f"[Embedder] provider init failed ({e}); falling back to CPUExecutionProvider")
            self.model = TextEmbedding(model_name=model_name, batch_size=batch_size, providers=["CPUExecutionProvider"])

        # Probe once to get dimension
        self.dim = len(list(self.model.embed(["probe"]))[0])
        print(f"[Embedder] Model '{model_name}' loaded. Dim={self.dim}")

    def embed(self, texts: Sequence[str]) -> List[List[float]]:
        """Return list[list[float]]; FastEmbed yields an iterator of vectors."""
        return [list(map(float, v)) for v in self.model.embed(list(texts))]


class SparseBM25:
    """Sparse embedding model wrapper (BM25)."""
    def __init__(self, model_name: str = "Qdrant/bm25"):
        self.model = SparseTextEmbedding(model_name=model_name)
        print(f"[SparseBM25] Model '{model_name}' loaded.")

    def embed(self, texts: Sequence[str]) -> List[Dict[str, Any]]:
        """
        Returns a list of dicts: {"indices": [...], "values": [...]}
        """
        out = []
        for obj in self.model.embed(texts):
            if isinstance(obj, dict):
                idx = obj.get("indices", [])
                val = obj.get("values", [])
            else:
                # FastEmbed SparseEmbedding
                idx = getattr(obj, "indices", [])
                val = getattr(obj, "values", [])
            out.append({"indices": list(map(int, idx)), "values": list(map(float, val))})
        return out