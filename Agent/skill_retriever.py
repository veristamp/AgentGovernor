"""
Skill Retriever for AgentGovernor.

Searches the mcp_skills Qdrant collection to find relevant skills
for a user's goal. This is the FIRST step in the Waterfall Architecture.

If a skill is found (high score), we use it as context for the LLM.
If no skill matches, we fall back to Tool Retriever for binding discovery.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from qdrant_client import QdrantClient, models as qm

from .embedder import Embedder, SparseBM25
from .skill_loader import Skill, load_skill
from . import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s skill_retriever :: %(message)s"
)
log = logging.getLogger("skill_retriever")

# Skill collection name
SKILL_COLLECTION_NAME = "mcp_skills"

# Threshold for considering a skill a "hit"
# RRF scores are typically in the 0.01-0.05 range
# A score of 0.025+ indicates a good match (appears in top positions in multiple batches)
SKILL_HIT_THRESHOLD = 0.025

try:
    dense_embedder = Embedder(model_name=config.DENSE_EMBED_MODEL)
    sparse_embedder = SparseBM25(model_name=config.SPARSE_EMBED_MODEL)
    qdrant_client = QdrantClient(url=config.QDRANT_URL)
    log.info(f"Skill retriever connected to Qdrant at {config.QDRANT_URL}")
except Exception as e:
    log.critical(f"Failed to initialize skill retriever: {e}", exc_info=True)
    dense_embedder = None
    sparse_embedder = None
    qdrant_client = None


def find_relevant_skill(
    goal: str,
    skills_dir: Path = Path("skills"),
    top_k: int = 3
) -> Tuple[Optional[Skill], float]:
    """
    Search for a skill that matches the user's goal.
    
    This is the Waterfall Gatekeeper - if we find a matching skill,
    we can skip tool retrieval entirely.
    
    Args:
        goal: The user's goal/query
        skills_dir: Path to skills directory (for loading full skill)
        top_k: Number of candidates to consider
    
    Returns:
        Tuple of (Skill, score) if found, (None, 0.0) otherwise
    """
    if not all([qdrant_client, dense_embedder, sparse_embedder]):
        log.error("Skill retriever not initialized. Falling back to tool retrieval.")
        return None, 0.0
    
    log.info(f"Searching for skill matching goal: '{goal[:50]}...'")
    
    try:
        # Check if collection exists
        collections = qdrant_client.get_collections()
        collection_names = [c.name for c in collections.collections]
        if SKILL_COLLECTION_NAME not in collection_names:
            log.warning(f"Collection '{SKILL_COLLECTION_NAME}' not found. No skills indexed yet.")
            return None, 0.0
        
        # Embed the goal
        dense_vec = dense_embedder.embed([goal])[0]
        sparse_vec_data = sparse_embedder.embed([goal])[0]
        
        sparse_vec = qm.SparseVector(
            indices=sparse_vec_data["indices"],
            values=sparse_vec_data["values"]
        )
        
        # Build hybrid search
        query_requests = [
            qm.QueryRequest(
                query=dense_vec,
                using='dense',
                limit=config.HYBRID_CANDIDATE_COUNT,
                with_payload=True,
                with_vector=False
            )
        ]
        
        if sparse_vec.indices and sparse_vec.values:
            query_requests.append(qm.QueryRequest(
                query=sparse_vec,
                using='bm25',
                limit=config.HYBRID_CANDIDATE_COUNT,
                with_payload=True,
                with_vector=False
            ))
        
        # Run search
        results_batches = qdrant_client.query_batch_points(
            collection_name=SKILL_COLLECTION_NAME,
            requests=query_requests
        )
        
        # RRF merge
        rrf_k = 60
        rankings = defaultdict(float)
        all_hits_map = {}
        
        for results_batch in results_batches:
            if not results_batch:
                continue
            for i, hit in enumerate(results_batch.points, start=1):
                hit_id = getattr(hit, "id")
                if hit_id:
                    rankings[hit_id] += (1.0 / (rrf_k + i))
                    all_hits_map[hit_id] = hit
        
        if not rankings:
            log.info("No skills found in search.")
            return None, 0.0
        
        # Get top result
        sorted_ids = sorted(rankings.keys(), key=lambda pid: rankings[pid], reverse=True)[:top_k]
        
        if not sorted_ids:
            return None, 0.0
        
        top_id = sorted_ids[0]
        top_hit = all_hits_map[top_id]
        top_score = rankings[top_id]
        
        payload = getattr(top_hit, "payload", {})
        skill_name = payload.get("name", "unknown")
        skill_path = payload.get("skill_path")
        
        log.info(f"Top skill match: {skill_name} (score: {top_score:.4f})")
        
        # Check if score meets threshold
        if top_score < SKILL_HIT_THRESHOLD:
            log.info(f"Score {top_score:.4f} below threshold {SKILL_HIT_THRESHOLD}. Falling back to tool retrieval.")
            return None, top_score
        
        # Load the full skill
        if skill_path:
            skill_md_path = Path(skill_path) / "SKILL.md"
            if skill_md_path.exists():
                skill = load_skill(skill_md_path)
                if skill:
                    log.info(f"✅ SKILL HIT: {skill.name}")
                    return skill, top_score
        
        # Fallback: try loading from skills_dir
        skill_folder = skills_dir / skill_name
        skill_md_path = skill_folder / "SKILL.md"
        if skill_md_path.exists():
            skill = load_skill(skill_md_path)
            if skill:
                log.info(f"✅ SKILL HIT: {skill.name}")
                return skill, top_score
        
        log.warning(f"Could not load skill {skill_name} from disk.")
        return None, top_score
        
    except Exception as e:
        log.error(f"Error searching for skills: {e}", exc_info=True)
        return None, 0.0


def get_skill_bindings(skill: Skill) -> List[str]:
    """
    Get the list of bindings (tools) required by a skill.
    
    This is used to inject only the necessary tool schemas
    into the sandbox when executing code based on a skill.
    """
    return skill.bindings


if __name__ == '__main__':
    # Test the retriever
    log.info("--- Running Skill Retriever Test ---")
    
    test_goal = "I want to work with Excel spreadsheets and formulas"
    
    if all([qdrant_client, dense_embedder, sparse_embedder]):
        skill, score = find_relevant_skill(test_goal)
        if skill:
            log.info(f"Found skill: {skill.name}")
            log.info(f"Bindings: {skill.bindings}")
            log.info(f"Score: {score:.4f}")
        else:
            log.info("No matching skill found")
    else:
        log.error("Skill retriever not initialized")
