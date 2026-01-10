#!/usr/bin/env python3
"""
Code Prompt Builder for Governed Code Mode.

Builds prompts that instruct the LLM to generate Python code
(with async def main()) instead of YAML workflows.

This is Pillar 3 of the Governed Code Mode architecture.
"""
from __future__ import annotations

import json
import logging
import textwrap
from typing import Any, Dict, List, Optional

from Agent.skill_loader import Skill

log = logging.getLogger("code_prompt_builder")


# --- System Prompts ---

SYSTEM_PROMPT_CODE = """You are The Code Orchestrator. Your job is to compile a user GOAL into executable Python code.

CRITICAL RULES:
1. You ONLY output a single Python code block - no explanations, no markdown outside the code block.
2. The code MUST define an `async def main()` function that will be executed.
3. You can use RAW BINDINGS or SKILL HELPERS:
   - Raw binding: `await filesystem.list_directory(path=".")`
   - Skill helper: `from skills import filesystem; await filesystem.list_files(".")`
4. Skills provide convenient helpers - prefer them when available.
5. All calls are async: use `await`
6. Return meaningful results from main() - this is what the user will see.
7. Include a # PLAN: comment at the top describing what the code does.

OUTPUT FORMAT:
```python
# PLAN: Brief description of what this code does

from skills import filesystem  # Optional: import skill helpers

async def main():
    # Your implementation here
    result = await filesystem.list_files(".")
    return result
```"""

SYSTEM_PROMPT_CODE_REPAIR = """You are a Python code auto-correcting bot. A user will provide broken Python code and a list of errors. Your ONLY job is to fix the code and return a single, corrected Python code block. Do not add any explanation."""


# --- Code Template ---

CODE_TEMPLATE = '''# PLAN: {goal_summary}

async def main():
    """
    Goal: {goal}
    """
    # Your implementation here
    pass
'''


def _format_binding_signature(tool: Dict[str, Any]) -> str:
    """
    Formats a tool as a binding signature for the LLM.
    
    Example output:
        filesystem.list_directory(path: str) -> List[Dict]
            Lists files and directories at the given path.
    """
    qname = tool.get("qualified_name", "unknown.unknown")
    desc = tool.get("description", "No description")
    schema = tool.get("schema", {})
    
    # Build parameter list
    props = schema.get("properties", {})
    required = set(schema.get("required", []))
    
    params = []
    for name, details in props.items():
        ptype = details.get("type", "any")
        if name in required:
            params.append(f"{name}: {ptype}")
        else:
            default = details.get("default", "None")
            params.append(f"{name}: {ptype} = {default}")
    
    param_str = ", ".join(params) if params else ""
    
    return f"""await {qname}({param_str})
    {desc}"""


def _format_bindings_section(tools: List[Dict[str, Any]]) -> str:
    """
    Formats all tools as available bindings for the code prompt.
    """
    if not tools:
        return "No bindings available."
    
    lines = ["## Available Bindings", ""]
    lines.append("These are the ONLY functions you can call. All are async (use await):")
    lines.append("")
    
    for tool in tools:
        lines.append(f"### `{tool.get('qualified_name', 'unknown')}`")
        lines.append(_format_binding_signature(tool))
        lines.append("")
    
    return "\n".join(lines)


def _format_skill_section(skill: Skill) -> str:
    """
    Formats a skill's content for inclusion in the prompt.
    """
    lines = [
        f"## Skill: {skill.name}",
        "",
        skill.description,
        "",
        "### Instructions and Examples:",
        "",
        skill.content,
        ""
    ]
    return "\n".join(lines)


def build_code_prompt(
    goal: str,
    retrieved_tools: List[Dict[str, Any]],
    skill: Optional[Skill] = None,
    examples: Optional[List[str]] = None
) -> str:
    """
    Builds the full prompt for code generation.
    
    Args:
        goal: The user's goal/request
        retrieved_tools: List of tool payloads from RAG
        skill: Optional skill that matched the goal
        examples: Optional list of example code snippets
    
    Returns:
        The complete prompt string
    """
    sections = []
    
    # --- Role Section ---
    sections.append("# ROLE")
    sections.append("You are The Code Orchestrator. Generate Python code to accomplish the user's goal.")
    sections.append("")
    
    # --- Goal Section ---
    sections.append("# GOAL")
    sections.append(goal)
    sections.append("")
    
    # --- Skill Section (if available) ---
    if skill:
        sections.append("# SKILL (Use this as your guide)")
        sections.append(_format_skill_section(skill))
        sections.append("")
    
    # --- Bindings Section ---
    sections.append("# AVAILABLE BINDINGS")
    sections.append(_format_bindings_section(retrieved_tools))
    sections.append("")
    
    # --- Constraints Section ---
    sections.append("# CONSTRAINTS")
    sections.append(textwrap.dedent("""
        1. Output ONLY a Python code block - no explanations before or after.
        2. Define exactly one `async def main()` function.
        3. You can use RAW BINDINGS or SKILL HELPERS:
           - Raw: `await filesystem.list_directory(path=".")` 
           - Skill: `from skills import filesystem; await filesystem.list_files(".")`
        4. ONLY `from skills import X` is allowed - no other imports.
        5. All calls are async: `result = await binding.method(arg=value)`
        6. Start with a `# PLAN:` comment describing what the code does.
        7. Return a meaningful result from main().
        8. Use standard Python: if/else, for loops, list comprehensions, etc.
        9. Handle errors gracefully with try/except when appropriate.
    """).strip())
    sections.append("")
    
    # --- Examples Section ---
    if examples:
        sections.append("# EXAMPLES")
        for i, example in enumerate(examples, 1):
            sections.append(f"## Example {i}")
            sections.append("```python")
            sections.append(example)
            sections.append("```")
            sections.append("")
    else:
        # Default example
        sections.append("# EXAMPLE OUTPUT FORMAT")
        sections.append("```python")
        sections.append(textwrap.dedent("""
            # PLAN: List Python files in current directory and count them
            
            from skills import filesystem  # Import skill helpers
            
            async def main():
                # Use skill helper for cleaner code
                py_files = await filesystem.find_by_extension(".", ".py")
                
                # Or use raw binding:
                # files = await filesystem.list_directory(path=".")
                # py_files = [f['name'] for f in files if f['name'].endswith('.py')]
                
                # Return result
                return {
                    "python_files": len(py_files),
                    "names": py_files
                }
        """).strip())
        sections.append("```")
        sections.append("")
    
    # --- Final Instruction ---
    sections.append("# YOUR TASK")
    sections.append(f"Generate Python code to accomplish: {goal}")
    sections.append("")
    sections.append("Output ONLY the Python code block:")
    
    return "\n".join(sections)


def build_repair_prompt(
    original_code: str,
    errors: List[str],
    goal: str
) -> str:
    """
    Builds a prompt for repairing broken code.
    
    Args:
        original_code: The code that failed validation
        errors: List of error messages from the auditor
        goal: The original goal (for context)
    
    Returns:
        The repair prompt string
    """
    sections = []
    
    sections.append("# CODE REPAIR REQUEST")
    sections.append("")
    sections.append("## Original Goal")
    sections.append(goal)
    sections.append("")
    sections.append("## Broken Code")
    sections.append("```python")
    sections.append(original_code)
    sections.append("```")
    sections.append("")
    sections.append("## Errors to Fix")
    for error in errors:
        sections.append(f"- {error}")
    sections.append("")
    sections.append("## Instructions")
    sections.append("Fix the errors above and return the corrected code.")
    sections.append("Output ONLY the fixed Python code block - no explanations.")
    
    return "\n".join(sections)


def extract_code_from_response(response: str) -> Optional[str]:
    """
    Extracts Python code from an LLM response.
    
    Handles:
    - Code wrapped in ```python ... ```
    - Code wrapped in ``` ... ```
    - Raw code (if it looks like Python)
    
    Returns:
        The extracted code, or None if extraction fails
    """
    import re
    
    # Try to find ```python ... ``` block
    pattern = r'```python\s*\n(.*?)```'
    match = re.search(pattern, response, re.DOTALL)
    if match:
        return match.group(1).strip()
    
    # Try to find ``` ... ``` block
    pattern = r'```\s*\n(.*?)```'
    match = re.search(pattern, response, re.DOTALL)
    if match:
        code = match.group(1).strip()
        # Verify it looks like Python
        if 'async def main' in code or 'def main' in code:
            return code
    
    # Check if the response itself is raw Python code
    response = response.strip()
    if response.startswith("# PLAN:") or "async def main" in response:
        return response
    
    return None


# --- Test ---
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    
    # Test with sample data
    test_tools = [
        {
            "qualified_name": "filesystem.list_directory",
            "description": "Lists files and directories at the given path.",
            "schema": {
                "properties": {
                    "path": {"type": "string", "description": "The directory path"}
                },
                "required": ["path"]
            }
        },
        {
            "qualified_name": "filesystem.read_file",
            "description": "Reads the content of a file.",
            "schema": {
                "properties": {
                    "path": {"type": "string", "description": "The file path"}
                },
                "required": ["path"]
            }
        }
    ]
    
    test_goal = "List all Python files in the current directory and show their names"
    
    prompt = build_code_prompt(test_goal, test_tools)
    print("=" * 60)
    print("GENERATED PROMPT:")
    print("=" * 60)
    print(prompt)
