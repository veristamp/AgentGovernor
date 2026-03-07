# file_patcher/manager.py
"""
File Patcher Manager - Unified Interface for Code Mutations.

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
    
    # Direct write
    success, receipt = await patcher.write("output.py", code)
"""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass

from config import get_logger

from .surgical import SurgicalPatcher, PatchReceipt
from .stitcher import FrankensteinStitcher, StitchResult
from .guards import guarded_write, validate_syntax_only, critique_only

logger = get_logger("FilePatcher")


@dataclass
class PatcherConfig:
    """Configuration for the file patcher."""
    # Judgment gates
    validate_syntax: bool = True
    run_critic: bool = False
    run_impact: bool = False
    run_tests: bool = False
    
    # Project
    project_root: Optional[str] = None
    staging_dir: str = "f:/kb/.staging"
    
    # Identity
    agent_id: str = "system"


class FilePatcherManager:
    """
    Unified facade for all file mutation operations.
    
    Layers:
    ┌──────────────────────────────────────────────────────────────┐
    │  FilePatcherManager  (this class)                            │
    │    patch() / create() / write()                              │
    ├──────────────────────────────────────────────────────────────┤
    │  SurgicalPatcher / FrankensteinStitcher                      │
    │    Chunk editing / File assembly                             │
    ├──────────────────────────────────────────────────────────────┤
    │  core.py primitives                                          │
    │    apply_patch / assemble / ripple / read / write            │
    ├──────────────────────────────────────────────────────────────┤
    │  guards.py                                                   │
    │    Judgment pipeline (validate, critic, impact, tests)       │
    └──────────────────────────────────────────────────────────────┘
    """
    
    def __init__(
        self,
        qdrant_client: Optional[Any] = None,
        session_maker: Optional[Any] = None,
        config: Optional[PatcherConfig] = None
    ):
        """
        Initialize the patcher manager.
        
        Args:
            qdrant_client: Qdrant client for vector operations
            session_maker: DB session maker for distributed locks
            config: Optional configuration
        """
        self.config = config or PatcherConfig()
        self._session_maker = session_maker
        
        # Initialize components
        self._patcher = SurgicalPatcher(
            qdrant_client=qdrant_client,
            staging_dir=self.config.staging_dir,
            agent_id=self.config.agent_id
        )
        
        self._stitcher = FrankensteinStitcher(
            validate=self.config.validate_syntax,
            critique=self.config.run_critic,
            impact=self.config.run_impact,
            test=self.config.run_tests,
            project_root=self.config.project_root
        )
    
    # =========================================================================
    # MAIN API (3 methods)
    # =========================================================================
    
    async def patch(
        self,
        file_path: str,
        collection: str,
        chunk: Dict[str, Any],
        new_content: str,
        embed_fn: Optional[callable] = None,
        dry_run: bool = False,
        staged: bool = False
    ) -> PatchReceipt:
        """
        Edit an existing chunk in a file.
        
        Args:
            file_path: Path to source file
            collection: Qdrant collection name
            chunk: Chunk metadata (id, index, offsets)
            new_content: New content for the chunk
            embed_fn: Optional embedding function
            dry_run: Validate without writing
            staged: Write to staging area
            
        Returns:
            PatchReceipt with results
        """
        return await self._patcher.patch(
            file_path=file_path,
            collection=collection,
            chunk=chunk,
            new_content=new_content,
            embed_fn=embed_fn,
            session_maker=self._session_maker,
            dry_run=dry_run,
            staged=staged,
            validate=self.config.validate_syntax,
            critique=self.config.run_critic,
            impact=self.config.run_impact,
            test=self.config.run_tests
        )
    
    async def create(
        self,
        grafts: List[Dict[str, Any]],
        output_path: str,
        overwrite: bool = False,
        dry_run: bool = False
    ) -> StitchResult:
        """
        Create a new file from grafts.
        
        Args:
            grafts: Source grafts (chunk dicts with source, start, end)
            output_path: Where to save
            overwrite: Allow overwriting
            dry_run: Validate without writing
            
        Returns:
            StitchResult with stats
        """
        return await self._stitcher.stitch_from_chunks(
            chunks=grafts,
            output_path=output_path,
            overwrite=overwrite,
            dry_run=dry_run,
            session_maker=self._session_maker
        )
    
    async def write(
        self,
        file_path: str,
        content: str,
        old_content: Optional[str] = None,
        dry_run: bool = False
    ) -> tuple:
        """
        Write content to file with judgment gates.
        
        Args:
            file_path: Target file
            content: Content to write
            old_content: Original content (read if not provided)
            dry_run: Validate without writing
            
        Returns:
            (success, receipt_dict)
        """
        return await guarded_write(
            file_path=file_path,
            new_content=content,
            old_content=old_content,
            dry_run=dry_run,
            validate_syntax=self.config.validate_syntax,
            run_critic=self.config.run_critic,
            run_impact=self.config.run_impact,
            run_tests=self.config.run_tests,
            project_root=self.config.project_root,
            session_maker=self._session_maker
        )
    
    # =========================================================================
    # UTILITIES
    # =========================================================================
    
    def validate_only(self, file_path: str, content: str) -> tuple:
        """Quick syntax validation (sync)."""
        return validate_syntax_only(file_path, content)
    
    def critique_only(
        self,
        old_content: str,
        new_content: str,
        chunk: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Quick diff critique (sync)."""
        return critique_only(old_content, new_content, chunk)


# =============================================================================
# FACTORY FUNCTION
# =============================================================================

def create_patcher_manager(
    qdrant_client: Optional[Any] = None,
    session_maker: Optional[Any] = None,
    **config_kwargs
) -> FilePatcherManager:
    """
    Create a FilePatcherManager.
    
    Args:
        qdrant_client: Qdrant client
        session_maker: DB session maker
        **config_kwargs: PatcherConfig fields
        
    Returns:
        Configured FilePatcherManager
    """
    config = PatcherConfig(**{
        k: v for k, v in config_kwargs.items()
        if hasattr(PatcherConfig, k)
    })
    
    return FilePatcherManager(
        qdrant_client=qdrant_client,
        session_maker=session_maker,
        config=config
    )
