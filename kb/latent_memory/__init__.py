"""
Latent Memory - Unified AI Memory Interface.

Simple 4-method API:
- prepare(session_id, query, chunks) → Build LLM prompt
- learn(session_id, query, chunks, response) → Save turn + extract citations
- feedback(chunk_ids, positive) → Record user 👍/👎
- forget(session_id) → Clear session

Example:
    from latent_memory import create_memory_manager
    
    llm = create_memory_manager(
        system_prompt="You are helpful.",
        pg_session=db
    )
    
    prompt = await llm.prepare("session_123", "How do I chunk?", chunks)
    # ... call LLM to get response ...
    await llm.learn("session_123", "How do I chunk?", chunks, response)

For low-level access, import directly:
- latent_memory.feedback: FeedbackManager, SoftFeedbackLoop, HardFeedbackLoop
- latent_memory.memory: MemoryOrchestrator, EpisodicMemory, SemanticMemory
- latent_memory.kv_cache: KVCacheManager
"""

from .feedback import (
    FeedbackManager, create_feedback_manager,
    FeedbackLoop, create_feedback_loop,  # Backwards compat
    SoftFeedbackLoop, HardFeedbackLoop,
    ChunkSignal, extract_citations,
)

from .kv_cache import KVCacheManager
from .context_rotator import ContextRotator, TokenBudget
from .manager import LatentMemoryManager, LatentConfig, create_memory_manager

# Memory subsystem (3-tier)
from .memory import (
    MemoryOrchestrator, create_orchestrator,
    EpisodicMemory, SemanticMemory, MemoryCompressor,
    Turn, Memory, MemoryConfig
)


# Re-export patcher from file_patcher for backwards compatibility
from file_patcher import (
    SurgicalPatcher, apply_surgical_patch, 
    FrankensteinStitcher, guarded_write,
    FilePatcherManager, create_patcher_manager,
)

# Re-export judgment layers for backwards compatibility
# New code should import directly from `judgment` module
from judgment import (
    # Manager (unified interface)
    JudgmentManager, create_judgment_manager, PatchEvaluation,
    # Validator
    PatchValidator, create_validator, validate_before_patch,
    # Critic
    DiffCritic, create_critic, Critique, Violation,
    # Oracle
    ImpactOracle, create_oracle, ImpactReport, RiskLevel,
    # Immune
    ImmuneSystem, create_immune_system, TestResult, PatchVerification,
    # VPC
    PatchLogger, PatchRecord, create_patch_logger,
)

__all__ = [
    # Main API (what most users need)
    "LatentMemoryManager",
    "LatentConfig",
    "create_memory_manager",
    
    # Feedback (for advanced use)
    "FeedbackManager",
    "create_feedback_manager",
    "FeedbackLoop",  # Backwards compat alias
    "create_feedback_loop",
    "SoftFeedbackLoop",
    "HardFeedbackLoop",
    "ChunkSignal",
    "extract_citations",
    
    # Low-level components (for power users)
    "KVCacheManager",
    "ContextRotator",
    "TokenBudget",
    
    # Memory subsystem
    "MemoryOrchestrator",
    "create_orchestrator",
    "EpisodicMemory",
    "SemanticMemory",
    "MemoryCompressor",
    "Turn",
    "Memory",
    "MemoryConfig",



    # Re-exports from file_patcher (for backwards compatibility)
    "SurgicalPatcher",
    "apply_surgical_patch",
    "FrankensteinStitcher",
    "guarded_write",
    "FilePatcherManager",
    "create_patcher_manager",
    
    # Re-exports from judgment (for backwards compatibility)
    "JudgmentManager",
    "create_judgment_manager",
    "PatchEvaluation",
    "PatchValidator",
    "create_validator",
    "validate_before_patch",
    "DiffCritic",
    "create_critic",
    "Critique",
    "Violation",
    "ImpactOracle",
    "create_oracle",
    "ImpactReport",
    "RiskLevel",
    "ImmuneSystem",
    "create_immune_system",
    "TestResult",
    "PatchVerification",
    "PatchLogger",
    "PatchRecord",
    "create_patch_logger",
]



