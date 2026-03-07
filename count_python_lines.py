#!/usr/bin/env python3
"""
Script to count Python files and total lines of code in the project.
Respects .gitignore rules.
"""

import os
import pathlib
from pathlib import Path
from typing import Set, List


def parse_gitignore(gitignore_path: Path) -> Set[str]:
    """Parse .gitignore file and return set of patterns to ignore."""
    ignore_patterns = set()
    
    if not gitignore_path.exists():
        return ignore_patterns
    
    with open(gitignore_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            # Skip empty lines and comments
            if line and not line.startswith('#'):
                ignore_patterns.add(line)
    
    return ignore_patterns


def should_ignore(path: Path, root: Path, ignore_patterns: Set[str]) -> bool:
    """Check if a path should be ignored based on .gitignore patterns."""
    relative_path = path.relative_to(root)
    path_str = str(relative_path).replace('\\', '/')
    
    for pattern in ignore_patterns:
        # Remove leading/trailing slashes for comparison
        pattern = pattern.strip('/')
        
        # Directory pattern (ends with /)
        if pattern.endswith('/'):
            pattern = pattern.rstrip('/')
            if path.is_dir() and (path_str == pattern or path_str.startswith(pattern + '/')):
                return True
        
        # Wildcard patterns
        elif '*' in pattern:
            # Simple glob matching
            if pattern.startswith('*'):
                suffix = pattern[1:]
                if path_str.endswith(suffix) or any(part.endswith(suffix) for part in path_str.split('/')):
                    return True
            elif pattern.endswith('*'):
                prefix = pattern[:-1]
                if path_str.startswith(prefix) or any(part.startswith(prefix) for part in path_str.split('/')):
                    return True
            elif '**' in pattern:
                # Match anywhere in path
                clean_pattern = pattern.replace('**/', '').replace('/**', '')
                if clean_pattern in path_str:
                    return True
        
        # Exact match or directory match
        else:
            if path_str == pattern or path_str.startswith(pattern + '/'):
                return True
            # Check if any parent directory matches
            if any(part == pattern for part in path_str.split('/')):
                return True
    
    return False


def count_python_files_and_lines(root_dir: str = '.') -> tuple[int, int, List[tuple[str, int]]]:
    """
    Count Python files and total lines of code, respecting .gitignore.
    
    Returns:
        tuple: (number of files, total lines, list of (filepath, line_count))
    """
    root = Path(root_dir).resolve()
    gitignore_path = root / '.gitignore'
    
    # Parse .gitignore
    ignore_patterns = parse_gitignore(gitignore_path)
    
    # Always ignore .git directory
    ignore_patterns.add('.git')
    
    total_files = 0
    total_lines = 0
    file_details = []
    
    # Walk through directory
    for py_file in root.rglob('*.py'):
        # Check if file should be ignored
        if should_ignore(py_file, root, ignore_patterns):
            continue
        
        # Check if any parent directory should be ignored
        skip = False
        for parent in py_file.parents:
            if parent == root:
                break
            if should_ignore(parent, root, ignore_patterns):
                skip = True
                break
        
        if skip:
            continue
        
        # Count lines in file
        try:
            with open(py_file, 'r', encoding='utf-8', errors='ignore') as f:
                lines = len(f.readlines())
            
            total_files += 1
            total_lines += lines
            
            relative_path = py_file.relative_to(root)
            file_details.append((str(relative_path), lines))
        
        except Exception as e:
            print(f"Warning: Could not read {py_file}: {e}")
    
    return total_files, total_lines, file_details


def main():
    """Main function to run the script."""
    # Get the script's directory as the root
    script_dir = Path(__file__).parent
    
    print("=" * 70)
    print("Python Code Counter (respects .gitignore)")
    print("=" * 70)
    print(f"\nScanning directory: {script_dir}\n")
    
    total_files, total_lines, file_details = count_python_files_and_lines(script_dir)
    
    # Sort files by line count (descending)
    file_details.sort(key=lambda x: x[1], reverse=True)
    
    # Print results
    print(f"{'File':<60} {'Lines':>8}")
    print("-" * 70)
    
    for filepath, lines in file_details:
        print(f"{filepath:<60} {lines:>8,}")
    
    print("=" * 70)
    print(f"{'TOTAL:':<60} {total_lines:>8,}")
    print(f"{'Number of Python files:':<60} {total_files:>8,}")
    print("=" * 70)
    
    # Calculate average
    if total_files > 0:
        avg_lines = total_lines / total_files
        print(f"\nAverage lines per file: {avg_lines:,.1f}")


if __name__ == "__main__":
    main()
