from __future__ import annotations
from typing import List, Any, Optional, Iterable
import logging

log = logging.getLogger("tiny_reranker")

try:
    from fastembed.rerank.cross_encoder import TextCrossEncoder as _FE_TextCrossEncoder 
except Exception as e:
    log.error(f"FATAL: Could not import TextCrossEncoder (from fastembed.rerank): {e}")
    _FE_TextCrossEncoder = None

class TinyReranker:
    """
    Clean reranker that ONLY uses fastembed.rerank.TextCrossEncoder.
    If it fails to load, it will act as a no-op.
    """

    def __init__(self, model: Optional[str] = None):
        self.engine: Any = None
        self.kind: str = "noop"

        name = model or "jinaai/jina-reranker-v1-turbo-en"

        if _FE_TextCrossEncoder is not None:
            try:
                self.engine = _FE_TextCrossEncoder(model_name=name)
                self.kind = "fe_ce"  # fastembed cross-encoder
                log.info(f"TinyReranker initialized with {name} (fastembed.rerank.TextCrossEncoder).")
            except Exception as e:
                log.error(f"Failed to load TextCrossEncoder '{name}': {e}. Reranker will be in no-op mode.")
                self.engine = None
                self.kind = "noop"
        else:
            log.error("--- TINY_RERANKER FAILED TO LOAD --- TextCrossEncoder not found. Reranker is in no-op mode.")

    def _build_doc(self, payload: dict) -> str:
        if not payload:
            return ""
        
        embed_text = (payload.get("description") or "").strip()
        if embed_text:
            return embed_text

        title = (payload.get("title") or "").strip()
        text  = (payload.get("text")  or payload.get("content") or "").strip()
        if title and text:
            return f"{title}\n{text}"
        return title or text

    def rerank(self, query: str, items: List[Any], top_n: int) -> List[Any]:
        if not items or self.engine is None or self.kind == "noop":
            return items

        n = max(0, min(top_n, len(items)))
        if n == 0:
            return []

        docs: List[str] = []
        for it in items:
            payload = getattr(it, "payload", {}) or {}
            docs.append(self._build_doc(payload))

        
        try:
            scores = list(self.engine.rerank(query, docs))
        except Exception as e:
            log.warning(f"[TinyReranker] Rerank call failed: {e}. Returning original order.")
            return items[:n]

        ranked_idx = sorted(range(len(items)), key=lambda i: (scores[i], -i), reverse=True)
        return [items[i] for i in ranked_idx[:n]]