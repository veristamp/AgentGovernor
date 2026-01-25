# file_patcher/stitcher.py
"""
Frankenstein Stitcher - Assemble new files from existing code chunks.

The "physical object" approach: instead of generating code from scratch,
graft together verified chunks from existing files.

Key insight: "The best code is code that already works."

Usage:
    from file_patcher import FrankensteinStitcher
    
    stitcher = FrankensteinStitcher()
    
    result = await stitcher.stitch(
        grafts=[
            {"source": "src/utils.py", "start": 0, "end": 500},
            {"source": "src/models.py", "start": 100, "end": 300, "glue": "# Adapter"},
        ],
        output_path="generated/hybrid.py"
    )
"""

from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

from config import get_logger
from .core import assemble, read_file, write_file
from .guards import guarded_write

logger = get_logger("Stitcher")


@dataclass
class StitchResult:
    """Result of a stitch operation."""
    success: bool = False
    output_path: str = ""
    grafts_count: int = 0
    bytes_assembled: int = 0
    glue_lines: int = 0
    sources: List[str] = field(default_factory=list)
    validation: Optional[Dict] = None
    error: Optional[str] = None
    dry_run: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "output_path": self.output_path,
            "grafts": self.grafts_count,
            "bytes_copied": self.bytes_assembled,
            "glue_lines": self.glue_lines,
            "sources": self.sources,
            "validation": self.validation,
            "error": self.error,
            "dry_run": self.dry_run
        }


class FrankensteinStitcher:
    """
    Assembles new files from existing code chunks.
    
    Features:
    - Byte-precise grafting from verified source files
    - Optional glue code between grafts
    - Judgment validation before writing
    - Comment header injection (language-aware)
    """
    
    def __init__(
        self,
        validate: bool = True,
        critique: bool = False,
        impact: bool = False,
        test: bool = False,
        project_root: Optional[str] = None
    ):
        """
        Initialize the stitcher.
        
        Args:
            validate: Run syntax validation on result
            critique: Run diff critique (less useful for new files)
            impact: Run impact analysis
            test: Run related tests
            project_root: Project root for test discovery
        """
        self.validate = validate
        self.critique = critique
        self.impact = impact
        self.test = test
        self.project_root = project_root
    
    async def stitch(
        self,
        grafts: List[Dict[str, Any]],
        output_path: str,
        overwrite: bool = False,
        dry_run: bool = False,
        session_maker: Optional[Any] = None
    ) -> StitchResult:
        """
        Assemble a new file from grafts.
        
        Args:
            grafts: List of graft specs:
                {
                    "source": str,        # Source file path
                    "start": int,         # Start offset
                    "end": int,           # End offset
                    "comment": str?,      # Optional header comment
                    "glue": str?          # Optional code to append
                }
            output_path: Where to save the new file
            overwrite: Allow overwriting existing files
            dry_run: Validate without writing
            session_maker: DB session for VPC logging
            
        Returns:
            StitchResult with assembly stats
        """
        result = StitchResult(output_path=output_path)
        output_path = Path(output_path)
        
        # Check overwrite
        if output_path.exists() and not overwrite:
            result.error = f"Output exists: {output_path}"
            return result
        
        try:
            # 1. Load source files
            sources = {}
            for graft in grafts:
                src = graft.get("source") or graft.get("source_path")
                if src not in sources:
                    content, err = read_file(src)
                    if err:
                        result.error = err
                        return result
                    sources[src] = content
                    result.sources.append(src)
            
            # 2. Build assembly with comments
            parts = []
            for graft in grafts:
                src = graft.get("source") or graft.get("source_path")
                start = graft.get("start", 0)
                end = graft.get("end", 0)
                
                # Optional comment header
                comment = graft.get("comment")
                if comment:
                    parts.append(self._format_comment(src, comment))
                
                # Extract chunk
                chunk = sources[src][start:end]
                parts.append(chunk)
                result.bytes_assembled += len(chunk)
                result.grafts_count += 1
                
                # Optional glue
                glue = graft.get("glue")
                if glue:
                    parts.append(glue)
                    result.glue_lines += glue.count('\n') + 1
            
            assembled = "\n".join(parts)
            
            # 3. Get old content (empty for new files)
            old_content = ""
            if output_path.exists():
                old_content, _ = read_file(str(output_path))
                old_content = old_content or ""
            
            # 4. Write with guards
            success, receipt = await guarded_write(
                file_path=str(output_path),
                new_content=assembled,
                old_content=old_content,
                dry_run=dry_run,
                validate_syntax=self.validate,
                run_critic=self.critique,
                run_impact=self.impact,
                run_tests=self.test,
                project_root=self.project_root,
                session_maker=session_maker
            )
            
            result.success = success
            result.validation = receipt.get("validation")
            result.dry_run = dry_run
            
            if not success:
                result.error = receipt.get("error", "Write failed")
            else:
                logger.info(
                    f"✅ Stitched {result.grafts_count} grafts -> {output_path.name}"
                )
            
        except Exception as e:
            logger.exception("Stitch failed")
            result.error = str(e)
        
        return result
    
    async def stitch_from_chunks(
        self,
        chunks: List[Dict[str, Any]],
        output_path: str,
        overwrite: bool = False,
        dry_run: bool = False,
        session_maker: Optional[Any] = None
    ) -> StitchResult:
        """
        Stitch from chunk metadata (from Qdrant/DB).
        
        Convenience method that converts chunk dicts to graft format.
        
        Args:
            chunks: Chunk dicts with source, char offsets
            output_path: Where to save
            overwrite: Allow overwriting
            dry_run: Validate only
            session_maker: DB session
            
        Returns:
            StitchResult
        """
        grafts = []
        
        for chunk in chunks:
            graft = {
                "source": chunk.get("source") or chunk.get("file_path"),
                "start": chunk.get("processed_char_start", chunk.get("char_start", 0)),
                "end": chunk.get("processed_char_end", chunk.get("char_end", 0)),
            }
            
            if chunk.get("glue"):
                graft["glue"] = chunk["glue"]
            
            grafts.append(graft)
        
        return await self.stitch(
            grafts=grafts,
            output_path=output_path,
            overwrite=overwrite,
            dry_run=dry_run,
            session_maker=session_maker
        )
    
    def _format_comment(self, file_path: str, comment: str) -> str:
        """Format comment based on file extension."""
        ext = Path(file_path).suffix
        
        if ext in (".py", ".sh", ".yaml", ".yml"):
            return f"# {comment}"
        elif ext in (".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".c", ".cpp", ".java"):
            return f"// {comment}"
        elif ext in (".html", ".xml"):
            return f"<!-- {comment} -->"
        elif ext in (".css", ".scss"):
            return f"/* {comment} */"
        else:
            return f"# {comment}"


def create_stitcher(**kwargs) -> FrankensteinStitcher:
    """Factory function for FrankensteinStitcher."""
    return FrankensteinStitcher(**kwargs)
