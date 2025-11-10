#!/usr/bin/env python3
"""
Module for building the RICECO prompt for the planner LLM.

** MODIFIED to dynamically retrieve workflow examples **
"""
from __future__ import annotations

import json
import textwrap
import logging
from typing import Any, Dict, List

# --- Import the new workflow retriever ---
from Agent.workflow_retriever import find_relevant_workflows

# Get the planner's logger
log = logging.getLogger("planner")


def _format_schema(schema: Dict[str, Any], indent: int = 2) -> str:
    """
    Recursively formats a JSON schema into a readable string.
    This is the NEW, more detailed formatter.
    """
    indent_str = "  " * indent
    lines = []
    
    props = schema.get("properties", {})
    if not props:
        # Handle schemas defined with $defs (like memory.create_entities)
        defs = schema.get("$defs", {})
        if defs:
            for def_name, def_schema in defs.items():
                # Attempt to find the main properties within defs
                def_props = def_schema.get("properties")
                if def_props:
                    # Found properties, format them
                    req_args = set(def_schema.get("required", []))
                    for arg_name, details in def_props.items():
                        lines.append(f"{indent_str}- {arg_name}: ({details.get('type', 'any')}){' (required)' if arg_name in req_args else ''}")
                
                # Check for array items referencing defs
                for prop_name, prop_details in schema.get("properties", {}).items():
                    if prop_details.get("items", {}).get("$ref") == f"#/$defs/{def_name}":
                        lines.insert(0, f"{indent_str}- {prop_name}: (array of objects)")
                        lines.insert(1, f"{indent_str}  - object fields:")
            
            if lines:
                return "\n".join(lines)

        return "" # No properties found

    req_args = set(schema.get("required", []))
    
    for arg_name, details in props.items():
        arg_type = details.get("type", "any")
        req_str = " (required)" if arg_name in req_args else ""
        
        if arg_type == "object" and "properties" in details:
            lines.append(f"{indent_str}- {arg_name}:{req_str} (object):")
            lines.append(_format_schema(details, indent + 1))
        elif arg_type == "array":
            item_details = details.get("items", {})
            item_type = item_details.get("type", "any")
            
            # Check if array items are objects defined in $defs
            ref = item_details.get("$ref")
            if ref and ref.startswith("#/$defs/"):
                def_name = ref.split('/')[-1]
                def_schema = schema.get("$defs", {}).get(def_name, {})
                lines.append(f"{indent_str}- {arg_name}:{req_str} (array of objects):")
                lines.append(f"{indent_str}  - object fields:")
                lines.append(_format_schema(def_schema, indent + 2))
            elif item_type == "object" and "properties" in item_details:
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
- `description:` (optional) a human-readable goal for the workflow.
- `vars:` (optional) a map for variables.
- `steps:` is a map where each key is a unique *step_id*.
- Each step is a map containing a `tool:` name, `args:`, and optional `depends_on:`.
- `args:` are interpolated: `"${{vars.var_name}}"` or `"${{steps.step_id.output}}"`. **THIS IS A STRICT REQUIREMENT.**
- `depends_on:` is a list of *step_id* strings to wait for.
- `save_as:` (optional) saves a tool's output to `steps.step_id.output`.
- `log:` can be used instead of `tool:` to print a message.
"""

    # --- E: Examples (NEW: Dynamic RAG) ---
    log.info("Retrieving dynamic workflow examples...")
    try:
        # Call the new retriever
        workflow_examples = find_relevant_workflows(goal, top_k=3)
    except Exception as e:
        log.error(f"Failed to retrieve workflow examples: {e}. Falling back to no examples.")
        workflow_examples = []
    
    if workflow_examples:
        example_lines = ["EXAMPLES:", "---"]
        for i, yaml_example in enumerate(workflow_examples, 1):
            # Clean up the YAML string for insertion
            clean_yaml = textwrap.dedent(yaml_example).strip()
            example_lines.append(f"Example {i} (from a similar past workflow):\n```yaml\n{clean_yaml}\n```\n---")
        examples = "\n".join(example_lines)
    else:
        log.warning("No relevant workflow examples found. Proceeding without examples.")
        examples = "EXAMPLES:\n(No relevant examples found. You must create a plan from scratch.)"


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