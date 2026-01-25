# judgment/validator.py
"""
Semantic Validator - Pre-flight syntax checking for patches.

Uses tree-sitter (already in the project) to parse the *patched* buffer
before writing to disk. If the patch introduces syntax errors, we reject it.

This is the first layer of the "Senior Engineer in a Box" architecture:
- Syntactically valid patches by construction
- No more "the LLM forgot an indent" bugs

Usage:
    from judgment.validator import PatchValidator
    
    validator = PatchValidator()
    result = validator.validate_patch_preview(file_path, chunk_metadata, new_content)
    
    if not result.valid:
        print(f"Patch rejected: {result.error}")
        print(f"Error at line {result.error_line}: {result.error_context}")
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
import difflib
import os

from config import get_logger

logger = get_logger("Validator")

# Tree-sitter integration (reuse existing infrastructure)
try:
    from tree_sitter_language_pack import get_parser
    TREE_SITTER_AVAILABLE = True
except ImportError:
    TREE_SITTER_AVAILABLE = False
    logger.warning("tree-sitter-language-pack not available. Syntax validation disabled.")


# =============================================================================
# LANGUAGE MAPPING (Reuse from chunker)
# =============================================================================

EXTENSION_TO_LANGUAGE = {
    "py": "python", "python": "python",
    "js": "javascript", "jsx": "javascript", "javascript": "javascript",
    "ts": "typescript", "typescript": "typescript", "tsx": "tsx",
    "go": "go", "java": "java", "cpp": "cpp", "cc": "cpp", "c": "c", 
    "rs": "rust", "rb": "ruby", "php": "php", "cs": "c_sharp",
    "html": "html", "htm": "html", "css": "css", 
    "json": "json", "yaml": "yaml", "yml": "yaml",
    "sh": "bash", "bash": "bash"
}


# =============================================================================
# RESULT DATACLASSES
# =============================================================================

@dataclass
class ValidationResult:
    """Result of syntax validation."""
    valid: bool
    language: str
    error: Optional[str] = None
    error_line: Optional[int] = None
    error_column: Optional[int] = None
    error_context: Optional[str] = None  # The line containing the error
    node_count: int = 0  # Number of AST nodes parsed (for diagnostics)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "valid": self.valid,
            "language": self.language,
            "error": self.error,
            "error_line": self.error_line,
            "error_column": self.error_column,
            "error_context": self.error_context,
            "node_count": self.node_count,
        }


@dataclass
class PreviewResult:
    """Result of patch preview with validation."""
    valid: bool
    validation: ValidationResult
    diff_lines: List[str] = field(default_factory=list)  # Unified diff output
    old_content: str = ""
    new_content: str = ""
    patch_size: int = 0  # Bytes changed
    lines_changed: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "valid": self.valid,
            "validation": self.validation.to_dict(),
            "diff_lines": self.diff_lines[:50],  # Truncate for display
            "patch_size": self.patch_size,
            "lines_changed": self.lines_changed,
        }


# =============================================================================
# VALIDATOR CLASS
# =============================================================================

class PatchValidator:
    """
    Validates patches before they are applied to disk.
    
    Uses tree-sitter to parse the patched buffer and detect syntax errors.
    This prevents the most common class of LLM-induced bugs:
    - Indentation errors (Python)
    - Missing braces (JS/Go/Rust)
    - Unclosed strings
    - Invalid syntax constructs
    """
    
    def __init__(self, strict_mode: bool = True):
        """
        Initialize the validator.
        
        Args:
            strict_mode: If True, reject patches with ANY syntax errors.
                        If False, only reject if errors are in the patched region.
        """
        self.strict_mode = strict_mode
        self._parser_cache: Dict[str, Any] = {}
    
    def get_language(self, file_path: str) -> Optional[str]:
        """Determine tree-sitter language from file extension."""
        ext = Path(file_path).suffix.lower().lstrip(".")
        return EXTENSION_TO_LANGUAGE.get(ext)
    
    def _get_parser(self, language: str):
        """Get or create a parser for the given language."""
        if not TREE_SITTER_AVAILABLE:
            return None
        
        if language not in self._parser_cache:
            try:
                self._parser_cache[language] = get_parser(language)
            except Exception as e:
                logger.warning(f"Could not get parser for {language}: {e}")
                return None
        
        return self._parser_cache[language]
    
    def _find_errors(self, node, code_bytes: bytes, depth: int = 0) -> List[Tuple[int, int, str, str]]:
        """
        Recursively find actual ERROR nodes in the AST.
        
        Only captures actual ERROR or MISSING nodes, not parent nodes that 
        just have has_error=True due to a child error.
        
        Returns list of (line, column, error_type, error_text) tuples.
        """
        errors = []
        
        # Only capture actual ERROR or MISSING nodes
        if node.type == "ERROR" or node.type == "MISSING":
            line = node.start_point[0]
            col = node.start_point[1]
            # Get the actual problematic text
            error_text = code_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="replace")
            error_text = error_text[:50].strip()  # Truncate for display
            errors.append((line, col, node.type, error_text))
        
        # Recurse into children
        for child in node.children:
            errors.extend(self._find_errors(child, code_bytes, depth + 1))
        
        return errors
    
    def _count_nodes(self, node) -> int:
        """Count total AST nodes (for diagnostics)."""
        count = 1
        for child in node.children:
            count += self._count_nodes(child)
        return count
    
    def validate_syntax(
        self, 
        content: str, 
        language: str
    ) -> ValidationResult:
        """
        Validate that content is syntactically valid for the given language.
        
        Args:
            content: Source code to validate
            language: Tree-sitter language name (e.g., "python", "javascript")
            
        Returns:
            ValidationResult with valid=True or error details
        """
        if not TREE_SITTER_AVAILABLE:
            if self.strict_mode:
                return ValidationResult(
                    valid=False,
                    language=language,
                    error="CRITICAL: Tree-sitter is NOT available but required. Fix installation."
                )
            
            # Graceful degradation only if NOT in strict mode
            logger.debug("Tree-sitter unavailable, skipping validation (NON-STRICT)")
            return ValidationResult(
                valid=True,
                language=language,
                error="Tree-sitter unavailable - validation skipped"
            )
        
        parser = self._get_parser(language)
        if parser is None:
            if self.strict_mode:
                return ValidationResult(
                    valid=False,
                    language=language,
                    error=f"CRITICAL: No parser found for language '{language}' in strict mode."
                )
            return ValidationResult(
                valid=True,
                language=language,
                error=f"No parser for language: {language}"
            )
        
        try:
            # Parse the content
            content_bytes = bytes(content, "utf-8")
            tree = parser.parse(content_bytes)
            root = tree.root_node
            
            # Count nodes for diagnostics
            node_count = self._count_nodes(root)
            
            # Find errors
            errors = self._find_errors(root, content_bytes)
            
            if errors:
                # Get first error details
                line, col, error_type, error_text = errors[0]
                
                # Extract context (the line containing the error)
                lines = content.split("\n")
                error_context = lines[line] if line < len(lines) else ""
                
                # Build a useful error message
                if error_type == "MISSING":
                    error_msg = f"Missing expected token at line {line + 1}, column {col}"
                elif error_text:
                    error_msg = f"Unexpected token '{error_text}' at line {line + 1}, column {col}"
                else:
                    error_msg = f"Syntax error at line {line + 1}, column {col}"
                
                return ValidationResult(
                    valid=False,
                    language=language,
                    error=error_msg,
                    error_line=line + 1,  # 1-indexed for humans
                    error_column=col,
                    error_context=error_context,
                    node_count=node_count
                )
            
            return ValidationResult(
                valid=True,
                language=language,
                node_count=node_count
            )
            
        except Exception as e:
            logger.exception("Validation failed")
            return ValidationResult(
                valid=False,
                language=language,
                error=f"Validation exception: {str(e)}"
            )
    
    def validate_file(self, file_path: str) -> ValidationResult:
        """
        Validate an existing file on disk.
        
        Args:
            file_path: Path to the file
            
        Returns:
            ValidationResult
        """
        if not os.path.exists(file_path):
            return ValidationResult(
                valid=False,
                language="unknown",
                error=f"File not found: {file_path}"
            )
        
        language = self.get_language(file_path)
        if language is None:
            return ValidationResult(
                valid=True,
                language="unknown",
                error="Unsupported file type - validation skipped"
            )
        
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        return self.validate_syntax(content, language)
    
    def validate_patch_preview(
        self,
        file_path: str,
        chunk_metadata: Dict[str, Any],
        new_content: str,
        include_diff: bool = True
    ) -> PreviewResult:
        """
        Validate a patch BEFORE applying it.
        
        This is the key "Senior Engineer" gate:
        1. Construct the patched buffer in memory
        2. Parse it with tree-sitter
        3. Reject if syntax errors detected
        4. Return a diff preview for review
        
        Args:
            file_path: Path to the target file
            chunk_metadata: Chunk dict with char offsets
            new_content: The new text to insert
            include_diff: Whether to include unified diff in result
            
        Returns:
            PreviewResult with validation status and diff
        """
        # 1. Read the original file
        if not os.path.exists(file_path):
            return PreviewResult(
                valid=False,
                validation=ValidationResult(
                    valid=False,
                    language="unknown",
                    error=f"File not found: {file_path}"
                )
            )
        
        with open(file_path, "r", encoding="utf-8") as f:
            original_content = f.read()
        
        # 2. Get character offsets
        start = chunk_metadata.get("processed_char_start")
        end = chunk_metadata.get("processed_char_end")
        
        if start is None or end is None:
            return PreviewResult(
                valid=False,
                validation=ValidationResult(
                    valid=False,
                    language="unknown",
                    error="Chunk metadata missing character offsets"
                )
            )
        
        # 3. Construct the patched buffer
        patched_content = original_content[:start] + new_content + original_content[end:]
        
        # 4. Determine language
        language = self.get_language(file_path)
        if language is None:
            # Unsupported language - skip validation but allow patch
            return PreviewResult(
                valid=True,
                validation=ValidationResult(
                    valid=True,
                    language="unknown",
                    error="Unsupported file type - validation skipped"
                ),
                old_content=original_content[start:end],
                new_content=new_content,
                patch_size=abs(len(new_content) - (end - start))
            )
        
        # 5. Validate the ORIGINAL file first (to establish baseline)
        original_validation = self.validate_syntax(original_content, language)
        
        # 6. Validate the PATCHED content
        patched_validation = self.validate_syntax(patched_content, language)
        
        # 7. Determine if the patch INTRODUCED errors
        # If the original was already broken, we're more lenient
        if self.strict_mode:
            # Strict: patched must be valid
            patch_valid = patched_validation.valid
        else:
            # Lenient: patched must not be WORSE than original
            if original_validation.valid:
                patch_valid = patched_validation.valid
            else:
                # Original was broken - just check we didn't add MORE errors
                # This is a simplification; full implementation would count errors
                patch_valid = True  # Allow editing broken files
        
        # 8. Generate diff for review
        diff_lines = []
        lines_changed = 0
        
        if include_diff:
            original_lines = original_content.splitlines(keepends=True)
            patched_lines = patched_content.splitlines(keepends=True)
            
            diff = difflib.unified_diff(
                original_lines,
                patched_lines,
                fromfile=f"{file_path} (original)",
                tofile=f"{file_path} (patched)",
                lineterm=""
            )
            diff_lines = list(diff)
            
            # Count lines changed (rough estimate)
            lines_changed = sum(1 for line in diff_lines if line.startswith(("+", "-")) and not line.startswith(("+++", "---")))
        
        return PreviewResult(
            valid=patch_valid,
            validation=patched_validation,
            diff_lines=diff_lines,
            old_content=original_content[start:end],
            new_content=new_content,
            patch_size=abs(len(new_content) - (end - start)),
            lines_changed=lines_changed
        )


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def create_validator(strict_mode: bool = True) -> PatchValidator:
    """Factory function to create a PatchValidator instance."""
    return PatchValidator(strict_mode=strict_mode)


def validate_before_patch(
    file_path: str,
    chunk_metadata: Dict[str, Any],
    new_content: str
) -> Tuple[bool, str]:
    """
    Quick validation check for use in patcher.py.
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    validator = PatchValidator()
    result = validator.validate_patch_preview(file_path, chunk_metadata, new_content)
    
    if result.valid:
        return True, ""
    else:
        error = result.validation.error or "Unknown validation error"
        if result.validation.error_line:
            error += f" at line {result.validation.error_line}"
        if result.validation.error_context:
            error += f": {result.validation.error_context[:50]}"
        return False, error
