#!/usr/bin/env python3
"""
Module for building the RICECO prompt for the planner LLM.
"""
from __future__ import annotations

import json
import textwrap
from typing import Any, Dict, List


EXAMPLE_A = """
Example A:
```yaml
version: 1
vars:
  workdir: "./_test_workflow"
steps:
  setup_dir:
    tool: filesystem.create_directory
    args:
      path: "${vars.workdir}"
  
  list_files:
    tool: filesystem.list_directory
    args:
      path: "."
    save_as: "file_list"

  write_report:
    tool: filesystem.write_file
    args:
      path: "${vars.workdir}/report.txt"
      content: "Files found: ${steps.list_files.output}"
    depends_on:
      - "setup_dir"
      - "list_files"
```
"""

EXAMPLE_B = """
Example B:
```yaml
version: 1
vars:
  entity: "Alice"
steps:
  create_person:
    tool: memory.create_entities
    args:
      entities:
        - name: "${vars.entity}"
          entityType: "Person"
          observations: ["Works in finance"]
    
  find_person:
    tool: memory.search_nodes
    args:
      query: "${vars.entity}"
    depends_on:
      - "create_person"
```
"""

EXAMPLE_C = """
Example C:
```yaml
version: 1
vars:
  command_to_run: "echo 'Hello from the terminal'"
steps:
  run_echo:
    tool: terminal.run_command
    args:
      command: "${vars.command_to_run}"
      timeout: 30
    save_as: "echo_output"

  log_output:
    log: "Terminal output was: ${steps.run_echo.output}"
    depends_on:
      - "run_echo"
```
"""

HARDCODED_EXAMPLES = [EXAMPLE_A, EXAMPLE_B, EXAMPLE_C]

def _format_tools_for_context(tools: List[Dict[str, Any]]) -> str:
    """
    Converts the list of retrieved tool payloads into a compact
    string for the LLM's context.
    """
    if not tools:
        return "No relevant tools found for this goal."
    
    lines = []
    for tool in tools:
        qname = tool.get('qualified_name', 'unknown.tool')
        desc = tool.get('description', 'No description.')
        
        schema = tool.get('schema', {})
        props = schema.get('properties', {})
        arg_list = []
        if props:
            req_args = set(schema.get('required', []))
            for arg_name, arg_details in props.items():
                arg_type = arg_details.get('type', 'any')
                req_str = " (required)" if arg_name in req_args else ""
                arg_list.append(f"{arg_name}: {arg_type}{req_str}")
        
        if arg_list:
            lines.append(f"- `tool: {qname}`")
            lines.append(f"  description: {desc}")
            lines.append(f"  args: {{{', '.join(arg_list)}}}")
        else:
            lines.append(f"- `tool: {qname}`")
            lines.append(f"  description: {desc}")
            lines.append(f"  args: {{}}")
            
    return "\n".join(lines)


def build_planner_prompt(goal: str, retrieved_tools: List[Dict[str, Any]]) -> str:
    """
    Builds the full RICECO prompt string.
    """
    
    # --- R: Role ---
    role = (
        "You are **The Orchestrator**. Your job is to compile a user GOAL into a "
        "deterministic YAML workflow plan. You never execute code or explain reasoning; "
        "you *only* emit a single, valid YAML code block."
    )

    # --- I: Instruction ---
    instruction = f"""
Given the user's GOAL, produce the smallest, most correct YAML workflow plan using *only* the tools provided in the CONTEXT.

**CRITICAL SYNTAX RULE:**
- Variables from `vars:` *must* be `"${{vars.variable_name}}"`.
- Outputs from other steps *must* be `"${{steps.step_id.output}}"`.

GOAL: "{goal}"
"""

    # --- C: Context ---
    tool_context = _format_tools_for_context(retrieved_tools)
    context = f"""
CONTEXT:
Available Tools:
{tool_context}

Workflow YAML Schema:
- The top level must be a map containing `version: 1` and `steps:`.
- `vars:` is an optional map for variables.
- `steps:` is a map where each key is a unique *step_id*.
- Each step is a map containing a `tool:` name, `args:`, and optional `depends_on:`.
- `args:` are interpolated: `"${{vars.var_name}}"` or `"${{steps.step_id.output}}"`. **THIS IS A STRICT REQUIREMENT.**
- `depends_on:` is a list of *step_id* strings to wait for.
- `save_as:` (optional) saves a tool's output to `steps.step_id.output`.
- `log:` can be used instead of `tool:` to print a message.
"""

    # --- E: Examples ---
    examples = "\n".join(HARDCODED_EXAMPLES)

    # --- CO: Constraints ---
    constraints = """
CONSTRAINTS:
1.  **CRITICAL SYNTAX:** Variables from the `vars:` block *must* be referenced as `"${vars.variable_name}"`. Step outputs *must* be referenced as `"${steps.step_id.output}"`. Any other format (like `${variable_name}`) is invalid and will fail.
2.  **Use ONLY the tools listed in the 'Available Tools' section.** Do not invent tools or arguments.
3.  Emit *only one* fenced YAML code block. Do not add any explanation, preamble, or apology.
4.  Ensure the YAML is valid. All strings must be quoted.
5.  Use `vars:` for any ambiguous values from the GOAL (like filenames or paths) if not provided.
6.  Create a logical `step_id` for every step (e.g., `list_files`, `write_report`).
7.  `depends_on:` is critical for sequential tasks. If a step uses the output of another, it *must* depend on it.
8.  Be as simple as possible. Do not add steps that were not requested by the GOAL.
"""

    # --- O: Output ---
    output_format = """
OUTPUT:
```yaml
version: 1
vars:
  # ... (optional)
steps:
  # ... (your plan)
```
"""

    # --- Assemble RICECO ---
    full_prompt = f"""
{role}
{instruction}
{context}
{examples}
{constraints}
{output_format}
"""
    return textwrap.dedent(full_prompt)

if __name__ == '__main__':
    # Example test
    print("--- Testing Prompt Builder ---")
    test_tools = [
        {
            "qualified_name": "filesystem.list_directory",
            "description": "Lists files and directories at a given path.",
            "schema": {
                "properties": {
                    "path": {"type": "string", "description": "The directory to list."},
                },
                "required": ["path"]
            }
        },
        {
            "qualified_name": "filesystem.write_file",
            "description": "Writes text content to a file.",
            "schema": {
                "properties": {
                    "path": {"type": "string", "description": "The file to write to."},
                    "content": {"type": "string", "description": "The text to write."}
                },
                "required": ["path", "content"]
            }
        }
    ]
    test_goal = "List all files in the root directory and save the list to a file named 'listing.txt'."
    
    prompt = build_planner_prompt(test_goal, test_tools)
    
    print(prompt)
    print("\n--- Prompt Length ---")
    print(f"{len(prompt)} characters")