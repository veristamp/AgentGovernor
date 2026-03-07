# services/pr_scanner/diff_parser.py
"""
Git Diff Parser - Converts unified diff format to structured data.

Handles:
- Unified diff parsing (git diff output)
- Hunk extraction with line ranges
- File change type detection
- Content reconstruction from diff
"""

import re
from typing import List, Optional, Tuple
from pathlib import Path

from config import get_logger, get_language_from_extension
from .core import FileChange, FileChangeType, DiffHunk

logger = get_logger("DiffParser")


# =============================================================================
# PATTERNS
# =============================================================================

# Matches: diff --git a/file.py b/file.py
DIFF_HEADER_PATTERN = re.compile(r'^diff --git a/(.+) b/(.+)$')

# Matches: --- a/file.py or --- /dev/null
OLD_FILE_PATTERN = re.compile(r'^--- (?:a/)?(.+)$')

# Matches: +++ b/file.py or +++ /dev/null
NEW_FILE_PATTERN = re.compile(r'^\+\+\+ (?:b/)?(.+)$')

# Matches: @@ -1,5 +1,7 @@ optional context
HUNK_HEADER_PATTERN = re.compile(r'^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)$')

# Matches: rename from/to
RENAME_FROM_PATTERN = re.compile(r'^rename from (.+)$')
RENAME_TO_PATTERN = re.compile(r'^rename to (.+)$')


# =============================================================================
# DIFF PARSER
# =============================================================================

class DiffParser:
    """
    Parses unified diff format into structured FileChange objects.
    
    Designed to work with:
    - git diff output
    - GitHub PR diff API (application/vnd.github.diff)
    - GitLab MR diff API
    """
    
    def __init__(self, project_root: Optional[str] = None):
        """
        Initialize parser.
        
        Args:
            project_root: Optional root path for resolving file contents
        """
        self.project_root = Path(project_root) if project_root else None
    
    def parse(self, diff_text: str) -> List[FileChange]:
        """
        Parse a complete diff into structured file changes.
        
        Args:
            diff_text: Full unified diff output
            
        Returns:
            List of FileChange objects
        """
        if not diff_text.strip():
            return []
        
        file_changes = []
        current_file: Optional[FileChange] = None
        current_hunk: Optional[DiffHunk] = None
        hunk_lines: List[str] = []
        
        lines = diff_text.split('\n')
        i = 0
        
        while i < len(lines):
            line = lines[i]
            
            # New file diff starts
            header_match = DIFF_HEADER_PATTERN.match(line)
            if header_match:
                # Save previous file if exists
                if current_file:
                    if current_hunk and hunk_lines:
                        current_hunk.content = '\n'.join(hunk_lines)
                        current_file.hunks.append(current_hunk)
                    file_changes.append(current_file)
                
                # Start new file
                old_path = header_match.group(1)
                new_path = header_match.group(2)
                
                current_file = FileChange(
                    path=new_path,
                    change_type=FileChangeType.MODIFIED,
                    old_path=old_path if old_path != new_path else None,
                    language=self._detect_language(new_path)
                )
                current_hunk = None
                hunk_lines = []
                i += 1
                continue
            
            if current_file is None:
                i += 1
                continue
            
            # File mode/rename detection
            if line.startswith('new file mode'):
                current_file.change_type = FileChangeType.ADDED
            elif line.startswith('deleted file mode'):
                current_file.change_type = FileChangeType.DELETED
            elif line.startswith('rename from'):
                current_file.change_type = FileChangeType.RENAMED
                match = RENAME_FROM_PATTERN.match(line)
                if match:
                    current_file.old_path = match.group(1)
            elif line.startswith('rename to'):
                match = RENAME_TO_PATTERN.match(line)
                if match:
                    current_file.path = match.group(1)
            
            # Old/new file paths (confirm detection)
            elif line.startswith('--- '):
                match = OLD_FILE_PATTERN.match(line)
                if match and match.group(1) == '/dev/null':
                    current_file.change_type = FileChangeType.ADDED
            
            elif line.startswith('+++ '):
                match = NEW_FILE_PATTERN.match(line)
                if match and match.group(1) == '/dev/null':
                    current_file.change_type = FileChangeType.DELETED
            
            # Hunk header
            elif line.startswith('@@'):
                # Save previous hunk
                if current_hunk and hunk_lines:
                    current_hunk.content = '\n'.join(hunk_lines)
                    current_file.hunks.append(current_hunk)
                
                match = HUNK_HEADER_PATTERN.match(line)
                if match:
                    current_hunk = DiffHunk(
                        old_start=int(match.group(1)),
                        old_count=int(match.group(2) or 1),
                        new_start=int(match.group(3)),
                        new_count=int(match.group(4) or 1),
                        content="",
                        header=line
                    )
                    hunk_lines = []
            
            # Diff content lines
            elif current_hunk is not None:
                if line.startswith(('+', '-', ' ', '\\')):
                    hunk_lines.append(line)
            
            i += 1
        
        # Save the last file
        if current_file:
            if current_hunk and hunk_lines:
                current_hunk.content = '\n'.join(hunk_lines)
                current_file.hunks.append(current_hunk)
            file_changes.append(current_file)
        
        # Reconstruct old/new content for each file
        for fc in file_changes:
            fc.old_content, fc.new_content = self._reconstruct_content(fc)
        
        logger.debug(f"Parsed {len(file_changes)} file changes from diff")
        return file_changes
    
    def _reconstruct_content(self, file_change: FileChange) -> Tuple[str, str]:
        """
        Reconstruct old and new content from diff hunks.
        
        For modified files, attempts to read original from disk if available.
        """
        old_lines = []
        new_lines = []
        
        for hunk in file_change.hunks:
            for line in hunk.content.split('\n'):
                if not line:
                    continue
                if line.startswith('-') and not line.startswith('---'):
                    old_lines.append(line[1:])
                elif line.startswith('+') and not line.startswith('+++'):
                    new_lines.append(line[1:])
                elif line.startswith(' '):
                    old_lines.append(line[1:])
                    new_lines.append(line[1:])
                elif line.startswith('\\'):
                    # "\ No newline at end of file"
                    pass
        
        old_content = '\n'.join(old_lines)
        new_content = '\n'.join(new_lines)
        
        # For modified files, try to get full context from disk
        if (file_change.change_type == FileChangeType.MODIFIED 
            and self.project_root 
            and not old_lines):
            try:
                full_path = self.project_root / file_change.path
                if full_path.exists():
                    old_content = full_path.read_text(encoding='utf-8')
            except Exception as e:
                logger.debug(f"Could not read original file: {e}")
        
        return old_content, new_content
    
    def _detect_language(self, path: str) -> Optional[str]:
        """Detect language from file extension."""
        ext = Path(path).suffix.lstrip('.')
        return get_language_from_extension(ext)


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def parse_diff(diff_text: str, project_root: Optional[str] = None) -> List[FileChange]:
    """
    Quick function to parse a diff.
    
    Args:
        diff_text: Unified diff text
        project_root: Optional project root for content resolution
        
    Returns:
        List of FileChange objects
    """
    parser = DiffParser(project_root=project_root)
    return parser.parse(diff_text)


def filter_changes(
    changes: List[FileChange],
    skip_patterns: Optional[List[str]] = None,
    max_lines: int = 5000
) -> List[FileChange]:
    """
    Filter file changes based on patterns and size limits.
    
    Args:
        changes: List of file changes
        skip_patterns: Glob patterns to skip (e.g., ["*.lock", "*.min.js"])
        max_lines: Maximum lines per file to review
        
    Returns:
        Filtered list of changes
    """
    import fnmatch
    
    skip_patterns = skip_patterns or []
    filtered = []
    
    for change in changes:
        # Check skip patterns
        should_skip = False
        for pattern in skip_patterns:
            if fnmatch.fnmatch(change.path, pattern):
                should_skip = True
                logger.debug(f"Skipping {change.path} (matches {pattern})")
                break
        
        if should_skip:
            continue
        
        # Check size limit
        total_lines = change.lines_added + change.lines_removed
        if total_lines > max_lines:
            logger.warning(f"Skipping {change.path} ({total_lines} lines > {max_lines} limit)")
            continue
        
        filtered.append(change)
    
    return filtered
