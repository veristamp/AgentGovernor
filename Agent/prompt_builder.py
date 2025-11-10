#!/usr/bin/env python3
"""
Module for building the RICECO prompt for the planner LLM.
"""
from __future__ import annotations

import json
import textwrap
from typing import Any, Dict, List

# --- EXAMPLES (Unchanged) ---
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
  workdir: "./_test_workflow_5"

# This workflow tests the 'if', 'loop', and 'set' logic blocks as
# nodes within the DAG.
steps:

  setup_dir:
    tool: filesystem.create_directory
    args:
      path: "${vars.workdir}"

  check_os:
    set:
      var: "is_windows"
      value: {"contains": [{"var": "env.OS"}, "Windows"]}

  run_if_block:
    if: {"var": "vars.is_windows"}
    then:
      - log: "This is a Windows environment."
    else:
      - log: "This is a Linux/macOS environment."
    depends_on:
      - "check_os"

  loop_create_files:
    loop:
      var: "filename"
      over: ["file_a.log", "file_b.log", "file_c.log"]
    do:
      - tool: filesystem.write_file
        args:
          path: "${vars.workdir}/${filename}"
          content: "This is log file ${filename}"
    depends_on:
      - "setup_dir"
  
  final_log:
    log: "Logic and Loop test complete. Check ${vars.workdir}."
    depends_on:
      - "run_if_block"
      - "loop_create_files"
```
"""

EXAMPLE_C = """
Example C:
```yaml
version: 1
vars:
  # --- Input Vars (what an LLM would customize) ---
  doc_library: "react"
  doc_topic: "hooks"
  code_target_function: "run_tool"
  code_target_path: "mcp_client/executioner.py"
  output_dir: "./_master_workflow_output"

steps:

  # --- Phase 1: Run parallel "fetch" tasks ---

  get_react_docs:
    tool: "context7.resolve-library-id"
    args:
      libraryName: "${vars.doc_library}"

  get_code_function:
    tool: "modelcontextprotocol-python-sdk.get-code"
    args:
      name: "${vars.code_target_function}"
      path: "${vars.code_target_path}"

  get_code_tree:
    tool: "modelcontextprotocol-python-sdk.folder-tree-structure"
    args:
      path: "mcp_client"

  setup_dir:
    tool: filesystem.create_directory
    args:
      path: "${vars.output_dir}"

  # --- Phase 2: Run tasks that depend on Phase 1 ---

  write_docs_to_file:
    tool: filesystem.write_file
    args:
      path: "${vars.output_dir}/react_docs_id.txt"
      # This step chains data from a DIFFERENT server (context7)
      content: "Docs for ${vars.doc_library}: ${steps.get_react_docs.output}"
    depends_on:
      - "get_react_docs"
      - "setup_dir" # Must wait for the dir to exist

  create_memory_entity:
    tool: memory.create_entities
    args:
      entities:
        - name: "CodeFunction"
          entityType: "WorkflowTest"
          # This step chains data from the SDK server
          observations: ["Fetched code for ${vars.code_target_function}"]
    depends_on:
      - "get_code_function" # Must wait for the code to be fetched

  # --- Phase 3: A "Join" step ---
  # This step must wait for filesystem, memory, and sdk tasks to all finish.

  list_final_directory:
    tool: terminal.run_command
    args:
      command: "ls -R ${vars.output_dir}"
    depends_on:
      - "write_docs_to_file"    # Depends on filesystem
      - "create_memory_entity"  # Depends on memory
      - "get_code_tree"         # Depends on sdk

  # --- Phase 4: Final Log ---

  final_log:
    log: |
      MASTER WORKFLOW COMPLETE.
      - Context7 Docs: ${steps.get_react_docs.output}
      - File Written: ${steps.write_docs_to_file.output}
      - Terminal Output: ${steps.list_final_directory.output}
    depends_on:
      - "list_final_directory"
```
"""

HARDCODED_EXAMPLES = [EXAMPLE_A, EXAMPLE_B, EXAMPLE_C]

def _format_schema(schema: Dict[str, Any], indent: int = 2) -> str:
    """
    Recursively formats a JSON schema into a readable string.
    This is the NEW, more detailed formatter.
    """
    indent_str = "  " * indent
    lines = []
    
    props = schema.get("properties", {})
    if not props:
        return ""

    req_args = set(schema.get("required", []))
    
    for arg_name, details in props.items():
        arg_type = details.get("type", "any")
        req_str = " (required)" if arg_name in req_args else ""
        
        if arg_type == "object" and "properties" in details:
            lines.append(f"{indent_str}- {arg_name}:{req_str} (object):")
            lines.append(_format_schema(details, indent + 1))
        elif arg_type == "array" and "items" in details.get("items", {}):
            item_details = details["items"]
            item_type = item_details.get("type", "any")
            if item_type == "object":
                lines.append(f"{indent_str}- {arg_name}:{req_str} (array of objects):")
                lines.append(f"{indent_str}  - object fields:")
                lines.append(_format_schema(item_details, indent + 2))
            else:
                lines.append(f"{indent_str}- {arg_name}:{req_str} (array of {item_type})")
        else:
            lines.append(f"{indent_str}- {arg_name}:{req_str} ({arg_type})")
            
    return "\n".join(lines)


def _format_tools_for_context(tools: List[Dict[str, Any]]) -> str:
    """
    Converts the list of retrieved tool payloads into a compact
    string for the LLM's context.
    
    ** MODIFIED to use _format_schema for better detail **
    """
    if not tools:
        return "No relevant tools found for this goal."
    
    lines = []
    for tool in tools:
        qname = tool.get('qualified_name', 'unknown.tool')
        desc = tool.get('description', 'No description.')
        schema = tool.get('schema', {})
        
        lines.append(f"tool: {qname}")
        lines.append(f"  description: {desc}")
        
        arg_schema_str = _format_schema(schema)
        if arg_schema_str:
            lines.append(f"  args:")
            lines.append(arg_schema_str)
        else:
            lines.append(f"  args: (none)")
        lines.append("") # Add a blank line for readability
            
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
2.  **Use ONLY the tools listed in the 'Available Tools' section.** Do not invent tools.
3.  **PAY CAREFUL ATTENTION to the 'args' schema for each tool.** You *must* provide all `(required)` arguments and respect the data types (string, array, object).
4.  Emit *only one* fenced YAML code block. Do not add any explanation, preamble, or apology.
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
            "qualified_name": "filesystem.write_file",
            "description": "Writes text content to a file.",
            "schema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "The file to write to."},
                    "content": {"type": "string", "description": "The text to write."}
                },
                "required": ["path", "content"]
            }
        },
        {
            "qualified_name": "memory.create_entities",
            "description": "Create multiple new entities in the knowledge graph",
            "schema": {
                "$defs": {
                    "Entity": {
                        "properties": {
                            "name": {"description": "The name of the entity", "type": "string"},
                            "entityType": {"description": "The type of the entity", "type": "string"},
                            "observations": {"description": "...", "type": "array", "items": {"type": "string"}}
                        },
                        "required": ["name", "entityType", "observations"],
                        "type": "object"
                    }
                },
                "properties": {
                    "entities": {
                        "items": {"$ref": "#/$defs/Entity"},
                        "title": "Entities",
                        "type": "array"
                    }
                },
                "required": ["entities"]
            }
        }
    ]
    test_goal = "Save 'hello' to test.txt and create a memory entity."
    
    prompt = build_planner_prompt(test_goal, test_tools)
    
    print(prompt)
    print("\n--- Prompt Length ---")
    print(f"{len(prompt)} characters")