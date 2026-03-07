"""
Skill Loader

Loads skill modules and injects `_bindings` (and `_binding` for single-binding skills).


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
import json
import importlib.util
import logging
from pathlib import Path
from types import ModuleType
from typing import Dict, Optional, Any

import mcp

logger = logging.getLogger("SkillLoader")



class SkillLoader:
    """
    Loads skill modules and injects bindings.
    
    Each skill module receives `_bindings` for server proxies and `_binding`
    for the single-binding convenience case.

    """
    
    def __init__(self, skills_dir: str = "skills"):
        self.skills_dir = Path(skills_dir)
        self.tools_dir = self.skills_dir.parent / "tools"
        self._loaded: Dict[str, ModuleType] = {}

    def _load_manifest(self, skill_name: str) -> Dict[str, object]:
        manifest_path = self.skills_dir / skill_name / "manifest.json"
        if not manifest_path.exists():
            return {"bindings": {skill_name: skill_name}}
        try:
            with manifest_path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid manifest.json for skill '{skill_name}': {exc}") from exc
        if not isinstance(data, dict):
            raise ValueError(f"Manifest for skill '{skill_name}' must be a JSON object")
        return data

    def _validate_bindings(self, skill_name: str, bindings: Dict[str, str]) -> None:
        if not self.tools_dir.exists():
            raise FileNotFoundError(
                f"Tools directory not found at {self.tools_dir}. Run list_tools.py first."
            )
        for alias, server_prefix in bindings.items():
            if not isinstance(server_prefix, str) or not server_prefix:
                raise ValueError(
                    f"Invalid binding for skill '{skill_name}': '{alias}' must map to a server name"
                )
            if not (self.tools_dir / server_prefix).is_dir():
                raise ValueError(
                    f"Skill '{skill_name}' binding '{alias}' references missing tool server '{server_prefix}'"
                )

    def _validate_fanout_tools(self, skill_name: str, fanout_tools: list[Any]) -> None:
        if not fanout_tools:
            return
        if not isinstance(fanout_tools, list):
            raise ValueError(f"Manifest for skill '{skill_name}' has invalid 'fanoutTools' section")
        for tool in fanout_tools:
            if not isinstance(tool, str) or '.' not in tool:
                raise ValueError(
                    f"Skill '{skill_name}' fanout tool '{tool}' must be a qualified tool name"
                )
            server_prefix, tool_name = tool.split('.', 1)
            tool_path = self.tools_dir / server_prefix / f"{tool_name}.json"
            if not tool_path.exists():
                raise ValueError(
                    f"Skill '{skill_name}' fanout tool '{tool}' not found at {tool_path}"
                )

    def _build_bindings(self, skill_name: str, manifest: Dict[str, object]) -> Dict[str, object]:
        bindings = manifest.get("bindings")
        if not bindings:
            bindings = {skill_name: skill_name}
        if not isinstance(bindings, dict):
            raise ValueError(f"Manifest for skill '{skill_name}' has invalid 'bindings' section")
        self._validate_bindings(skill_name, bindings)
        raw_fanout_tools = manifest.get("fanoutTools", [])
        fanout_tools = raw_fanout_tools if isinstance(raw_fanout_tools, list) else []
        self._validate_fanout_tools(skill_name, fanout_tools)
        skill_id = str(manifest.get("skillId", skill_name))
        version = str(manifest.get("version", 1))
        skill_ref = f"skills:{skill_id}@{version}"
        create_binding = getattr(mcp, "create_binding")
        return {
            alias: create_binding(server, skill_context=skill_ref)
            for alias, server in bindings.items()
        }
    
    def load(self, skill_name: str) -> ModuleType:

        """
        Load a skill module and inject bindings.
        
        Args:
            skill_name: Name of the skill (e.g., "filesystem", "memory")
        
        Returns:
            The loaded module with bindings injected

        """
        if skill_name in self._loaded:
            return self._loaded[skill_name]
        
        # Find the skill lib.py
        lib_path = self.skills_dir / skill_name / "lib.py"
        if not lib_path.exists():
            raise ImportError(f"Skill not found: {skill_name} (looked in {lib_path})")
        
        manifest = self._load_manifest(skill_name)
        bindings = self._build_bindings(skill_name, manifest)
        
        # Load the module

        spec = importlib.util.spec_from_file_location(
            f"skills.{skill_name}",
            lib_path
        )
        if spec is None or spec.loader is None:
            raise ImportError(f"Failed to load skill: {skill_name}")
        
        module = importlib.util.module_from_spec(spec)
        bindings_obj = bindings
        if len(bindings) == 1:
            bindings_obj = {"_binding": next(iter(bindings.values())), "_bindings": bindings}
        else:
            bindings_obj = {"_bindings": bindings}

        # Inject bindings BEFORE executing the module
        module.__dict__.update(bindings_obj)
        
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
    A package-like object that allows `import skills; skills.load("...")`.
    
    Example:
        import skills
        filesystem = skills.load("filesystem")
        
    It loads the requested skill with bindings injected.
    """
    
    def __init__(self, loader: SkillLoader):
        self._loader = loader

    def load(self, skill_name: str) -> ModuleType:
        """Load a skill by directory/skill id (supports kebab-case)."""
        return self._loader.load(skill_name)

    def list_available(self) -> list:
        return self._loader.list_available()
    
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
        import skills
        filesystem = skills.load("filesystem")
    """
    package = get_skills_package(skills_dir)
    sys.modules["skills"] = package  # type: ignore[assignment]
