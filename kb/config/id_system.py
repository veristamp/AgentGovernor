# config/id_system.py
"""
Central Stable ID System.
Ensures identical ID generation across Chunker, Harvester, and Ingestion.
"""

import hashlib

STABLE_ID_VERSION = 2  # Unified version for the entire Dual-Graph

def generate_stable_id(source_path: str, section_path: str, index: int) -> int:
    """
    Generates a globally stable 63-bit positive integer ID for a chunk.
    
    Formula: blake2b(AbsoluteSourcePath + SectionPath + Index + Version) & 0x7FFFFFFFFFFFFFFF
    
    Why 63 bits:
    - Postgres BigInt is SIGNED 64-bit: max = 2^63 - 1 = 9,223,372,036,854,775,807
    - Qdrant accepts unsigned 64-bit, so 63-bit positive values work fine
    - Using 63 bits ensures the SAME ID works in both systems without conversion
    
    This ID is:
    1. Deterministic (same content = same ID)
    2. Qdrant Compatible (fits in unsigned 64-bit)
    3. Postgres Compatible (fits in signed 64-bit / BigInt)
    4. Always positive (no signed/unsigned confusion)
    """
    seed = f"{source_path}::{section_path}::{index}::{STABLE_ID_VERSION}".encode("utf-8")
    full_hash = int.from_bytes(hashlib.blake2b(seed, digest_size=8).digest(), "big")
    
    # Mask to 63 bits to ensure it fits in both signed and unsigned int64
    return full_hash & 0x7FFFFFFFFFFFFFFF

def generate_section_anchor(source_path: str, section_path: str | None) -> str:
    """
    Stable hex anchor to group chunks under the same heading trail.
    Used for graph navigation and breadcrumb grouping.
    """
    seed = f"{source_path}||{section_path or 'root'}||{STABLE_ID_VERSION}".encode("utf-8")
    return hashlib.blake2b(seed, digest_size=16).hexdigest()
