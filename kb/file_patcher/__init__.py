# file_patcher/__init__.py
"""
File Patcher - Safe Code Mutations with Judgment Gates.

Simple 3-method API:
- patch(file, chunk, content)  → Edit existing chunk
- create(grafts, output)       → Assemble new file
- write(file, content)         → Direct guarded write

Usage:
    from file_patcher import create_patcher_manager
    
    patcher = create_patcher_manager(
        qdrant_client=qdrant,
        session_maker=db_session
    )
    
    # Edit a chunk
    result = await patcher.patch("src/main.py", "kb_chunks", chunk, new_code)
    
    # Create new file from existing chunks
    result = await patcher.create(chunks, "generated/hybrid.py")

For low-level access:
    from file_patcher import SurgicalPatcher, FrankensteinStitcher
    from file_patcher.core import apply_patch, assemble, ripple

Layer Structure:
┌─────────────────────────────────────────────────────────────────┐
│  FilePatcherManager           (High Level - 3 methods)          │
├─────────────────────────────────────────────────────────────────┤
│  SurgicalPatcher / Stitcher   (Mid Level - Operations)          │
├─────────────────────────────────────────────────────────────────┤
│  core.py                      (Low Level - Primitives)          │
│  apply_patch / assemble / ripple / read / write                 │
├─────────────────────────────────────────────────────────────────┤
│  guards.py                    (Judgment Pipeline)               │
│  validate_syntax / critique / impact / tests                    │
└─────────────────────────────────────────────────────────────────┘
"""

# Main API
from .manager import (
    FilePatcherManager,
    PatcherConfig,
    create_patcher_manager,
)

# Mid-level operations
from .surgical import (
    SurgicalPatcher,
    PatchReceipt,
    apply_surgical_patch,  # Legacy
    create_patcher,
)

from .stitcher import (
    FrankensteinStitcher,
    StitchResult,
    create_stitcher,
)

# Guards (for direct use)
from .guards import (
    guarded_write,
    run_judgment_pipeline,
    validate_syntax_only,
    critique_only,
)

# Low-level primitives
from .core import (
    apply_patch,
    assemble,
    ripple,
    update_embedding,
    PatchDelta,
    PatchResult,
)

__all__ = [
    # Main API
    "FilePatcherManager",
    "PatcherConfig",
    "create_patcher_manager",
    
    # Mid-level
    "SurgicalPatcher",
    "PatchReceipt",
    "apply_surgical_patch",
    "create_patcher",
    "FrankensteinStitcher",
    "StitchResult",
    "create_stitcher",
    
    # Guards
    "guarded_write",
    "run_judgment_pipeline",
    "validate_syntax_only",
    "critique_only",
    
    # Low-level
    "apply_patch",
    "assemble",
    "ripple",
    "update_embedding",
    "PatchDelta",
    "PatchResult",
]
