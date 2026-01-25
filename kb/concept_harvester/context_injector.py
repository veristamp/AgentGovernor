"""
Context Injector - Ghost Input Pattern for GLiNER

Injects document structure context into text before concept extraction
to disambiguate generic terms like "System", "Data", "Config".

Example:
    "System" in isolation → could mean anything
    "[CONTEXT: Qdrant | Vector Search] System" → GLiNER knows it's about Qdrant

Usage:
    injector = ContextInjector()
    
    # Single text
    enriched = injector.inject(text, section_path="Auth > Tokens")
    
    # Single chunk (returns enriched chunk with 'enriched_text' field)
    chunk = injector.inject_chunk(chunk)
    
    # Batch
    chunks = injector.inject_batch(chunks)
"""

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from config import get_logger

logger = get_logger("context_injector")

# Generic terms that need context to be useful
NOISE_TERMS = frozenset({
    "system", "data", "code", "file", "config", "setting",
    "object", "class", "function", "method", "module",
    "process", "service", "handler", "manager", "controller",
    "request", "response", "result", "output", "input",
    "value", "type", "model", "schema", "format"
})


@dataclass
class InjectionConfig:
    """Configuration for context injection."""
    prefix_template: str = "[CONTEXT: {context}]\n"
    max_prefix_chars: int = 150
    noise_terms: frozenset = field(default_factory=lambda: NOISE_TERMS)


class ContextInjector:
    """
    Injects document structure context into text before concept extraction.
    
    Implements "Breadcrumb + Root Topic" strategy:
    1. Extract root topic from section path or doc title
    2. Build condensed breadcrumb trail
    3. Inject as prefix for GLiNER disambiguation
    """
    
    def __init__(self, config: Optional[InjectionConfig] = None):
        self.config = config or InjectionConfig()
    
    # =========================================================================
    # CORE API
    # =========================================================================
    
    def inject(
        self,
        text: str,
        section_path: Optional[str] = None,
        root_topic: Optional[str] = None,
        doc_title: Optional[str] = None,
        chunk_type: str = "text"
    ) -> str:
        """
        Inject context prefix into text.
        
        Args:
            text: Raw text to enrich
            section_path: e.g. "Architecture > Auth > Tokens"
            root_topic: Override root topic
            doc_title: Fallback for root topic
            chunk_type: "text", "code", or "table"
            
        Returns:
            Text with context prefix
        """
        if not text or not text.strip():
            return text
        
        root = self._resolve_root_topic(root_topic, section_path, doc_title)
        breadcrumb = self._build_breadcrumb(section_path)
        
        if not root and not breadcrumb:
            return text
        
        prefix = self._format_prefix(root, breadcrumb, chunk_type)
        return f"{prefix}{text}"
    
    def inject_chunk(self, chunk: Dict[str, Any], root_topic: Optional[str] = None) -> Dict[str, Any]:
        """
        Inject context into a chunk dict.
        
        Adds 'enriched_text' field while preserving 'original_text'.
        Modifies chunk in-place and returns it.
        """
        text = chunk.get("original_text") or chunk.get("text", "")
        
        enriched = self.inject(
            text=text,
            section_path=chunk.get("section_path"),
            root_topic=root_topic,
            doc_title=self._clean_doc_title(chunk.get("source", "")),
            chunk_type=chunk.get("type", "text")
        )
        
        chunk["original_text"] = text
        chunk["enriched_text"] = enriched
        return chunk
    
    def inject_batch(
        self, 
        chunks: List[Dict[str, Any]], 
        root_topic: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Inject context into multiple chunks."""
        return [self.inject_chunk(c, root_topic) for c in chunks]
    
    # =========================================================================
    # NOISE HANDLING
    # =========================================================================
    
    def is_noise_candidate(self, term: str) -> bool:
        """Check if term is too generic without context."""
        return term.lower().strip() in self.config.noise_terms
    
    def disambiguate_term(
        self,
        term: str,
        section_path: Optional[str] = None,
        root_topic: Optional[str] = None
    ) -> str:
        """
        Disambiguate generic term using context.
        
        Example: "System" + root_topic="Qdrant" → "Qdrant System"
        """
        if not self.is_noise_candidate(term):
            return term
        
        context = root_topic or self._resolve_root_topic(None, section_path, None)
        return f"{context} {term}" if context else term
    
    # =========================================================================
    # INTERNAL HELPERS
    # =========================================================================
    
    def _resolve_root_topic(
        self,
        root_topic: Optional[str],
        section_path: Optional[str],
        doc_title: Optional[str]
    ) -> str:
        """Resolve root topic with fallback chain."""
        if root_topic:
            return root_topic.strip()
        
        if section_path:
            parts = section_path.split(" > ")
            if parts and parts[0].strip():
                return parts[0].strip()
        
        if doc_title:
            return self._clean_doc_title(doc_title).title()
        
        return ""
    
    def _build_breadcrumb(self, section_path: Optional[str]) -> str:
        """
        Build condensed breadcrumb from section path.
        
        "A > B > C > D" → "B | C" (skip first=root, last=current)
        """
        if not section_path:
            return ""
        
        parts = [p.strip() for p in section_path.split(" > ") if p.strip()]
        
        if len(parts) <= 2:
            return " | ".join(parts[1:]) if len(parts) > 1 else ""
        
        # Skip first (root) and last (current), limit to 3
        middle = parts[1:-1]
        if len(middle) > 3:
            middle = middle[:2] + ["..."] + middle[-1:]
        
        return " | ".join(middle)
    
    def _format_prefix(self, root: str, breadcrumb: str, chunk_type: str) -> str:
        """Format the context prefix string."""
        parts = [p for p in [root, breadcrumb] if p]
        
        if chunk_type == "code":
            parts.append("Code")
        elif chunk_type == "table":
            parts.append("Data")
        
        if not parts:
            return ""
        
        context = " | ".join(parts)
        if len(context) > self.config.max_prefix_chars:
            context = context[:self.config.max_prefix_chars - 3] + "..."
        
        return f"[CONTEXT: {context}]\n"
    
    def _clean_doc_title(self, title: str) -> str:
        """Clean filename-style title."""
        return re.sub(r'[-_.]', ' ', title.rsplit('.', 1)[0]) if title else ""


# Convenience function
def inject_context(
    chunks: List[Dict[str, Any]],
    root_topic: Optional[str] = None,
    config: Optional[InjectionConfig] = None
) -> List[Dict[str, Any]]:
    """Inject context into chunks (convenience wrapper)."""
    return ContextInjector(config).inject_batch(chunks, root_topic)
