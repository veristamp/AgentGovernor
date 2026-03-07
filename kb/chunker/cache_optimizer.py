"""
Caching layer for chunker to skip re-processing unchanged documents.

Usage:
    cache = ChunkCache("./chunk_cache")
    
    hash_key = cache.get_hash(content, url, settings)
    cached = cache.get(hash_key)
    
    if cached:
        return cached
    else:
        chunks = chunk_document(content, url, settings)
        cache.set(hash_key, chunks)
        return chunks
"""

import hashlib
import json
from pathlib import Path
from typing import Optional, List, Dict, Any


class ChunkCache:
    """
    File-based cache for chunker results using content hashing.
    
    Cache key = hash(content + url + settings_fingerprint)
    This means if the source file hasn't changed AND settings are identical,
    we skip re-chunking entirely (90% speedup).
    """
    
    def __init__(self, cache_dir: str = ".chunk_cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
    
    def get_hash(self, content: str, url: str, settings_dict: Dict) -> str:
        """Generate cache key from content + metadata"""
        # Include critical settings that affect output
        settings_str = json.dumps({
            "max_tokens": settings_dict.get("max_tokens_text", 2000),
            "overlap": settings_dict.get("overlap_tokens", 300),
            "inject_headers": settings_dict.get("inject_headers", True),
        }, sort_keys=True)
        
        combined = f"{content}{url}{settings_str}"
        return hashlib.sha256(combined.encode()).hexdigest()
    
    def get(self, hash_key: str) -> Optional[List[Dict[str, Any]]]:
        """Retrieve cached chunks if available"""
        cache_file = self.cache_dir / f"{hash_key}.json"
        if cache_file.exists():
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                return None
        return None
    
    def set(self, hash_key: str, chunks: List[Dict[str, Any]]):
        """Store chunks in cache"""
        cache_file = self.cache_dir / f"{hash_key}.json"
        try:
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(chunks, f)
        except Exception:
            pass  # Fail silently - cache is optional
    
    def clear(self):
        """Clear all cached chunks"""
        for cache_file in self.cache_dir.glob("*.json"):
            cache_file.unlink()

