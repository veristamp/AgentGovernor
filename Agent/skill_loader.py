"""
Skill Loader for AgentGovernor.

Parses SKILL.md files and loads skill metadata + content.
Skills are instruction manuals that teach the LLM how to use bindings properly.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger("skill_loader")


@dataclass
class Skill:
    """
    Represents a loaded skill.
    
    Skills are NOT executable code - they're instruction sets that provide:
    - Description: When to use this skill
    - Bindings: What MCP tools this skill uses
    - Instructions: Best practices, patterns, guidelines
    - Examples: Code patterns the LLM should follow
    """
    name: str
    description: str
    bindings: List[str]
    content: str  # The full markdown content (for LLM context)
    path: Path
    version: int = 1
    author: str = ""
    license: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "bindings": self.bindings,
            "version": self.version,
            "author": self.author,
            "path": str(self.path),
        }


def parse_skill_frontmatter(content: str) -> tuple[Dict[str, Any], str]:
    """
    Parse YAML frontmatter from SKILL.md.
    
    Expected format:
    ```
    ---
    name: skill-name
    description: What this skill does
    bindings:
      - tool.method
    ---
    # Content...
    ```
    
    Returns:
        Tuple of (frontmatter_dict, remaining_content)
    """
    # Match YAML frontmatter between --- markers
    pattern = r'^---\s*\n(.*?)\n---\s*\n(.*)$'
    match = re.match(pattern, content, re.DOTALL)
    
    if not match:
        log.warning("No frontmatter found in skill file")
        return {}, content
    
    frontmatter_text = match.group(1)
    body = match.group(2)
    
    # Simple YAML parsing (avoid dependency on PyYAML for this)
    metadata: Dict[str, Any] = {}
    current_key = None
    current_list: List[str] = []
    
    for line in frontmatter_text.split('\n'):
        line = line.rstrip()
        
        # Skip empty lines
        if not line.strip():
            continue
        
        # Check for list item
        if line.startswith('  - '):
            if current_key:
                current_list.append(line.strip()[2:])
            continue
        
        # Save previous list if exists
        if current_key and current_list:
            metadata[current_key] = current_list
            current_list = []
        
        # Parse key: value
        if ':' in line:
            key, _, value = line.partition(':')
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            
            if value:
                metadata[key] = value
            else:
                current_key = key
    
    # Save final list if exists
    if current_key and current_list:
        metadata[current_key] = current_list
    
    return metadata, body


def load_skill(skill_path: Path) -> Optional[Skill]:
    """
    Load a skill from a SKILL.md file.
    
    NEW: Auto-enriches with tool documentation from tools_schema.json.
    If bindings are not specified, they're auto-populated from schema.
    If binding docs aren't in the file, they're auto-appended.
    
    Args:
        skill_path: Path to the SKILL.md file
    
    Returns:
        Skill object or None if loading fails
    """
    from .schema_loader import generate_tool_docs, generate_bindings_list
    
    if not skill_path.exists():
        log.error(f"Skill file not found: {skill_path}")
        return None
    
    try:
        content = skill_path.read_text(encoding='utf-8')
    except Exception as e:
        log.error(f"Failed to read skill file {skill_path}: {e}")
        return None
    
    metadata, body = parse_skill_frontmatter(content)
    
    # Validate required fields
    name = metadata.get('name')
    description = metadata.get('description')
    
    if not name:
        log.error(f"Skill missing 'name' in frontmatter: {skill_path}")
        return None
    
    if not description:
        log.warning(f"Skill missing 'description' in frontmatter: {skill_path}") 
        description = body[:200] if body else "No description"
    
    # Parse bindings - auto-populate from schema if not specified
    bindings = metadata.get('bindings', [])
    if isinstance(bindings, str):
        bindings = [bindings]
    
    # AUTO-POPULATE: If no bindings specified, get from schema
    if not bindings:
        bindings = generate_bindings_list(name)
        if bindings:
            log.debug(f"Auto-populated {len(bindings)} bindings for skill '{name}'")
    
    # AUTO-ENRICH: Append tool docs from schema if not already in content
    # Check if content already has tool documentation
    has_tool_docs = "## Available Tools" in content or "## Available Bindings" in content
    
    if not has_tool_docs:
        auto_docs = generate_tool_docs(name)
        if auto_docs:
            content = content + auto_docs
            log.debug(f"Auto-appended tool docs for skill '{name}'")
    
    return Skill(
        name=name,
        description=description,
        bindings=bindings,
        content=content,  # Now includes auto-enriched docs
        path=skill_path.parent,
        version=int(metadata.get('version', 1)),
        author=metadata.get('author', ''),
        license=metadata.get('license', ''),
    )


def load_all_skills(skills_dir: Path) -> List[Skill]:
    """
    Load all skills from a directory.
    
    ONLY loads skills with SKILL.md files.
    NO virtual/auto-generated skills.
    
    Skills are Layer 2 abstraction - composed from Layer 1 tools.
    
    Args:
        skills_dir: Path to the skills directory
    
    Returns:
        List of loaded Skill objects
    """
    skills: List[Skill] = []
    
    if not skills_dir.exists():
        log.warning(f"Skills directory not found: {skills_dir}")
        return skills
    
    for skill_folder in skills_dir.iterdir():
        if not skill_folder.is_dir():
            continue
        
        skill_md = skill_folder / "SKILL.md"
        if not skill_md.exists():
            log.debug(f"Skipping {skill_folder.name}: no SKILL.md")
            continue
        
        skill = load_skill(skill_md)
        if skill:
            skills.append(skill)
            log.info(f"Loaded skill: {skill.name}")
    
    log.info(f"Loaded {len(skills)} skills from {skills_dir}")
    return skills


if __name__ == "__main__":
    # Test the loader
    import sys
    logging.basicConfig(level=logging.DEBUG)
    
    if len(sys.argv) > 1:
        skill_path = Path(sys.argv[1])
        if skill_path.is_file():
            skill = load_skill(skill_path)
        else:
            skills = load_all_skills(skill_path)
            for s in skills:
                print(f"- {s.name}: {s.description[:50]}...")
    else:
        # Default: load from ./skills
        skills = load_all_skills(Path("skills"))
