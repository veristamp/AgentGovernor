"""
Skill Loader

Loads skill modules and injects the `_binding` proxy into them.

The binding pattern ensures:
1. LLM never sees raw MCP tool names
2. All calls route through the Policy Gate
3. Skills handle parsing/formatting of results

Usage:
    skills = SkillLoader()
    filesystem = skills.load("filesystem")
    
    # Now in workflow:
    files = await filesystem.list_files(".")
"""

import sys
import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Dict, Optional

import mcp


class SkillLoader:
    """
    Loads skill modules and injects bindings.
    
    Each skill module expects a global `_binding` object that proxies
    method calls to the corresponding MCP server.
    """
    
    def __init__(self, skills_dir: str = "skills"):
        self.skills_dir = Path(skills_dir)
        self._loaded: Dict[str, ModuleType] = {}
    
    def load(self, skill_name: str) -> ModuleType:
        """
        Load a skill module and inject _binding.
        
        Args:
            skill_name: Name of the skill (e.g., "filesystem", "memory")
        
        Returns:
            The loaded module with _binding injected
        """
        if skill_name in self._loaded:
            return self._loaded[skill_name]
        
        # Find the skill lib.py
        lib_path = self.skills_dir / skill_name / "lib.py"
        if not lib_path.exists():
            raise ImportError(f"Skill not found: {skill_name} (looked in {lib_path})")
        
        # Create the binding proxy for this skill's server
        binding = mcp.create_binding(skill_name)
        
        # Load the module
        spec = importlib.util.spec_from_file_location(
            f"skills.{skill_name}",
            lib_path
        )
        if spec is None or spec.loader is None:
            raise ImportError(f"Failed to load skill: {skill_name}")
        
        module = importlib.util.module_from_spec(spec)
        
        # Inject _binding BEFORE executing the module
        module._binding = binding
        
        # Execute the module code
        spec.loader.exec_module(module)
        
        # Cache it
        self._loaded[skill_name] = module
        
        return module
    
    def get(self, skill_name: str) -> Optional[ModuleType]:
        """Get a loaded skill, or None if not loaded."""
        return self._loaded.get(skill_name)
    
    def list_available(self) -> list:
        """List all available skills."""
        if not self.skills_dir.exists():
            return []
        return [
            d.name for d in self.skills_dir.iterdir()
            if d.is_dir() and (d / "lib.py").exists()
        ]


# ============== Skills Package ==============

class SkillsPackage:
    """
    A package-like object that allows `from skills import filesystem` syntax.
    
    When you do:
        from skills import filesystem
        
    It loads the filesystem skill with _binding injected.
    """
    
    def __init__(self, loader: SkillLoader):
        self._loader = loader
    
    def __getattr__(self, name: str) -> ModuleType:
        if name.startswith('_'):
            raise AttributeError(name)
        return self._loader.load(name)


# ============== Global Instance ==============

_loader: Optional[SkillLoader] = None
_package: Optional[SkillsPackage] = None

def get_loader(skills_dir: str = "skills") -> SkillLoader:
    """Get the global skill loader."""
    global _loader
    if _loader is None:
        _loader = SkillLoader(skills_dir)
    return _loader

def get_skills_package(skills_dir: str = "skills") -> SkillsPackage:
    """Get the skills package for import-style access."""
    global _package
    if _package is None:
        _package = SkillsPackage(get_loader(skills_dir))
    return _package


# ============== Install as Package ==============

def install_skills_package(skills_dir: str = "skills"):
    """
    Install the skills package into sys.modules.
    
    After calling this, workflows can do:
        from skills import filesystem
        from skills import memory
    """
    package = get_skills_package(skills_dir)
    sys.modules["skills"] = package
