"""
Concept Harvester - Semantic Extraction Engine (v3.0)

Polymorphic extraction from chunks using GLiNER + AST metadata.

CHUNK TYPE STRATEGIES:
- TEXT   → GLiNER on prose
- CODE   → AST symbols + GLiNER on comments
- TABLE  → GLiNER on headers
- HEADING → Skip (structure only)

USAGE:
    harvester = ConceptHarvester()
    
    # Single chunk
    concepts = harvester.extract(chunk)
    
    # Batch (concurrent processing)
    results = harvester.batch_extract(chunks)  # Returns Dict[chunk_id → concepts]
    
    # Async
    results = await harvester.batch_extract_async(chunks)
"""

import asyncio
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, Union

from config import get_logger

logger = get_logger("concept_harvester")

# ChunkKeys with fallback
try:
    from config import ChunkKeys as K
except ImportError:
    class K:
        TYPE = "type"
        TEXT = "text"
        ORIGINAL_TEXT = "original_text"
        ID = "id"
        METADATA = "metadata"
        META_SYMBOLS = "symbols_defined"
        META_COMMENTS = "comments_text"
        META_HEADERS = "headers"

# Code noise
CODE_NOISE = frozenset({
    '__init__', '__str__', '__repr__', '__call__', '__enter__', '__exit__',
    '__len__', '__iter__', '__next__', '__getitem__', '__setitem__',
    'main', 'run', 'test', 'setup', 'teardown', 'init', 'get', 'set',
    'self', 'cls', 'args', 'kwargs', 'data', 'result', 'value', 'item',
    'config', 'options', 'params', 'settings', 'context', 'request', 'response',
})


def clean_concept_name(name: str) -> str:
    """Clean and validate a concept name."""
    if not name or len(name) < 3 or len(name) > 50:
        return ""
    
    name = name.strip()
    
    # Skip duplicate CamelCase (GLiNER artifact)
    words = re.findall(r'[A-Z][a-z]+', name)
    if len(words) >= 4 and words[:len(words)//2] == words[len(words)//2:len(words)//2*2]:
        return ""
    
    # Skip noise patterns
    if re.match(r'^[a-z_]+$|^\d+$|^[A-Z]{1,2}$', name):
        return ""
    
    # Strip articles
    for prefix in ('the ', 'a ', 'an '):
        if name.lower().startswith(prefix):
            name = name[len(prefix):]
            break
    
    return name.strip() if len(name) >= 3 else ""


class ConceptHarvester:
    """
    Polymorphic concept extraction engine.
    
    Uses GLiNER for semantic extraction and AST metadata for code symbols.
    """
    
    def __init__(self, config: Optional["HarvesterConfig"] = None):
        from .config import HarvesterConfig
        self.config = config or HarvesterConfig()
        self.model = None
        
        try:
            from gliner import GLiNER
            logger.info(f"🚀 Loading GLiNER: {self.config.model_name}")
            self.model = GLiNER.from_pretrained(self.config.model_name)
            self.model.to(self.config.device)
            if self.config.device == "cuda":
                self.model.half()
            logger.info(f"✓ GLiNER on {self.config.device}")
        except Exception as e:
            logger.warning(f"GLiNER unavailable: {e}")
    
    def _clean_text(self, text: str) -> str:
        """Prepare text for GLiNER."""
        if not text:
            return ""
        text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
        text = re.sub(r"https?://\S+", "", text)
        text = re.sub(r"\s+", " ", text)
        return text[:self.config.max_text_chars].strip()
    
    def _gliner(self, text: str) -> List[Dict[str, Any]]:
        """Run GLiNER on text."""
        if not self.model:
            return []
        
        clean = self._clean_text(text)
        if len(clean) < 20:
            return []
        
        try:
            entities = self.model.predict_entities(
                clean, self.config.ontology, threshold=self.config.base_threshold
            )
        except Exception as e:
            logger.debug(f"GLiNER failed: {e}")
            return []
        
        seen, results = set(), []
        for ent in entities:
            name = clean_concept_name(ent.get("text", ""))
            if not name or name.lower() in seen:
                continue
            seen.add(name.lower())
            
            concept = {"name": name, "type": ent.get("label", "Concept")}
            if self.config.include_scores:
                concept["score"] = round(float(ent.get("score", 0)), 3)
            results.append(concept)
        
        return results
    
    def _extract_code(self, metadata: Dict) -> List[Dict[str, Any]]:
        """Extract from code metadata (AST + comments)."""
        results = []
        
        for sym in metadata.get(K.META_SYMBOLS, []):
            name = sym.get("name", "")
            if name and len(name) >= 3 and not name.startswith("_") and name.lower() not in CODE_NOISE:
                results.append({
                    "name": name,
                    "type": f"Code:{sym.get('kind', 'symbol').title()}",
                    "score": 1.0
                })
        
        comments = metadata.get(K.META_COMMENTS, "")
        if comments and len(comments) > 20:
            results.extend(self._gliner(comments))
        
        return results
    
    def _extract_table(self, metadata: Dict) -> List[Dict[str, Any]]:
        """Extract from table headers."""
        headers = metadata.get(K.META_HEADERS, [])
        return self._gliner(" ".join(headers)) if headers else []
    
    # =========================================================================
    # PUBLIC API
    # =========================================================================
    
    def extract(self, chunk: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract concepts from a single chunk."""
        chunk_type = chunk.get(K.TYPE) or chunk.get("type", "text")
        metadata = chunk.get(K.METADATA) or chunk.get("metadata", {})
        
        if chunk_type == "text":
            text = chunk.get(K.ORIGINAL_TEXT) or chunk.get("original_text") or chunk.get(K.TEXT) or chunk.get("text", "")
            return self._gliner(text)
        elif chunk_type == "code":
            return self._extract_code(metadata)
        elif chunk_type == "table":
            return self._extract_table(metadata)
        return []
    
    def batch_extract(
        self, 
        items: Union[List[Dict[str, Any]], List[str]], 
        batch_size: Optional[int] = None
    ) -> Union[Dict[Any, List[Dict[str, Any]]], List[List[Dict[str, Any]]]]:
        """
        Batch extract concepts with concurrent processing.
        
        Args:
            items: List of chunk dicts OR list of plain text strings
            batch_size: Max concurrent workers (default from config)
            
        Returns:
            - If chunks: Dict[chunk_id → concepts]
            - If texts: List[concepts] in same order
        """
        if not items:
            return {} if isinstance(items, list) and items and isinstance(items[0], dict) else []
        
        # Detect input type
        is_text_list = isinstance(items[0], str)
        batch_size = batch_size or self.config.batch_size
        max_workers = min(batch_size, len(items), 8)
        
        if is_text_list:
            # Plain text strings
            results = [None] * len(items)
            
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {executor.submit(self._gliner, text): i for i, text in enumerate(items)}
                for future in as_completed(futures):
                    idx = futures[future]
                    try:
                        results[idx] = future.result()
                    except:
                        results[idx] = []
            
            return [r or [] for r in results]
        
        else:
            # Chunk dicts - separate by type
            text_items, other_items = [], []
            for chunk in items:
                cid = chunk.get(K.ID) or chunk.get("id")
                if not cid:
                    continue
                ctype = chunk.get(K.TYPE) or chunk.get("type", "text")
                
                if ctype == "text":
                    text = chunk.get(K.ORIGINAL_TEXT) or chunk.get("original_text") or chunk.get(K.TEXT) or chunk.get("text", "")
                    text_items.append((cid, text))
                elif ctype in ("code", "table"):
                    other_items.append((cid, chunk))
            
            results = {}
            
            # Concurrent text extraction
            if text_items and self.model:
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    futures = {executor.submit(self._gliner, text): cid for cid, text in text_items}
                    for future in as_completed(futures):
                        cid = futures[future]
                        try:
                            concepts = future.result()
                            if concepts:
                                results[cid] = concepts
                        except:
                            pass
            
            # Code/table (fast, sequential)
            for cid, chunk in other_items:
                concepts = self.extract(chunk)
                if concepts:
                    results[cid] = concepts
            
            return results
    
    async def batch_extract_async(
        self, 
        items: Union[List[Dict[str, Any]], List[str]], 
        batch_size: Optional[int] = None
    ) -> Union[Dict[Any, List[Dict[str, Any]]], List[List[Dict[str, Any]]]]:
        """Async wrapper for batch_extract."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: self.batch_extract(items, batch_size))


# Backward compat alias
Harvester = ConceptHarvester
