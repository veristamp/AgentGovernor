#!/usr/bin/env python3
"""
Module for validating the YAML plan from the LLM.
This is a new validator that checks against dynamically retrieved tools.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Set, Tuple

import yaml
from jsonschema import Draft7Validator, SchemaError, ValidationError
# Regex to find interpolations
VAR_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_\.]*)\}")

class PlanValidator:
    """
    Validates a PlanYAML string against a dynamic set of available tools.
    """
    def __init__(self, tools_payload_list: List[Dict[str, Any]]):
        self.tools_schema = self._build_tools_map(tools_payload_list)
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.all_step_ids: Set[str] = set()

    def _build_tools_map(self, tools_list: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Converts the Qdrant payload list into a map for easy lookup."""
        schema_map = {}
        for tool in tools_list:
            qname = tool.get("qualified_name")
            if qname:
                # The payload already has 'schema' hydrated by the retriever
                schema_map[qname] = tool.get("schema", {})
        return schema_map

    def validate(self, yaml_block: str) -> Tuple[Dict[str, Any] | None, List[str]]:
        """
        Main validation entrypoint.
        Returns (parsed_plan, list_of_errors)
        """
        self.errors = []
        self.warnings = []

        # 1. Parse YAML
        try:
            plan = yaml.safe_load(yaml_block)
        except yaml.YAMLError as e:
            return None, [f"YAML parse error: {e}"]
        
        if not isinstance(plan, dict):
            return None, ["Plan must be a top-level dictionary (map)."]

        # 2. Check top-level structure
        if plan.get("version") != 1:
            self.errors.append('Top-level "version" must be 1.')
        
        steps = plan.get("steps")
        if not isinstance(steps, dict):
            self.errors.append("'steps' must be a dictionary (map).")
            # Cannot continue validation without steps
            return plan, self.errors

        self.all_step_ids = set(steps.keys())

        # 3. Validate each step
        for step_id, config in steps.items():
            self._validate_step(step_id, config)

        # 4. Validate graph (cycles, dependencies)
        self._validate_graph(steps)
        
        return plan, self.errors

    def _validate_step(self, step_id: str, config: Any):
        """Validates a single step entry."""
        if not isinstance(config, dict):
            self.errors.append(f"Step '{step_id}': Configuration must be a map.")
            return

        # Check for 'tool' or 'log'
        if "tool" in config:
            self._validate_tool_step(step_id, config)
        elif "log" in config:
            # 'log' steps are simple
            if not isinstance(config["log"], str):
                self.errors.append(f"Step '{step_id}': 'log' value must be a string.")
        else:
            self.errors.append(f"Step '{step_id}': Must contain either 'tool' or 'log'.")
        
        # Check 'depends_on'
        if "depends_on" in config:
            deps = config["depends_on"]
            if not isinstance(deps, list):
                self.errors.append(f"Step '{step_id}': 'depends_on' must be a list.")
                return
            for dep_id in deps:
                if dep_id not in self.all_step_ids:
                    self.errors.append(f"Step '{step_id}': has missing dependency '{dep_id}'.")

    def _validate_tool_step(self, step_id: str, config: Dict[str, Any]):
        """Validates a 'tool' step."""
        tool_name = config.get("tool")
        if not isinstance(tool_name, str):
            self.errors.append(f"Step '{step_id}': 'tool' name must be a string.")
            return

        # Check if tool is one of the *retrieved* tools
        if tool_name not in self.tools_schema:
            self.errors.append(f"Step '{step_id}': Tool '{tool_name}' is not in the list of available tools.")
            return
        
        tool_schema = self.tools_schema[tool_name]
        tool_args = config.get("args", {})

        if not isinstance(tool_args, dict):
            self.errors.append(f"Step '{step_id}': 'args' must be a dictionary (map).")
            return
        
        # Validate arguments against the tool's JSON schema
        try:
            validator = Draft7Validator(tool_schema)
            for error in sorted(validator.iter_errors(tool_args), key=str):
                is_interpolation = isinstance(error.instance, str) and VAR_PATTERN.search(error.instance)
                
                # Don't flag 'type' errors for interpolation strings
                if error.validator == "type" and is_interpolation:
                    self.warnings.append(f"Step '{step_id}': Arg '{'.'.join(error.path)}' is dynamic. Type validation skipped.")
                # Flag 'required' errors even if interpolation is possible
                elif error.validator == "required":
                     self.errors.append(f"Step '{step_id}': Missing required arg '{error.message}'")
                else:
                    self.errors.append(f"Step '{step_id}' (Tool: {tool_name}): Arg error at '{'.'.join(error.path)}' - {error.message}")

        except SchemaError as e:
            self.errors.append(f"Step '{step_id}': Internal Schema Error for {tool_name}: {e}")

    def _validate_graph(self, steps: Dict[str, Any]):
        """Checks for cycles in the dependency graph."""
        path: Set[str] = set()
        visited: Set[str] = set()

        def visit(step_id: str):
            path.add(step_id)
            for dep_id in steps[step_id].get("depends_on", []):
                if dep_id not in self.all_step_ids:
                    continue # Already caught by missing dep check
                if dep_id in path:
                    cycle = " -> ".join(list(path) + [dep_id])
                    self.errors.append(f"Circular dependency (cycle) detected: {cycle}")
                    return
                if dep_id not in visited:
                    visit(dep_id)
            path.remove(step_id)
            visited.add(step_id)

        for step_id in self.all_step_ids:
            if step_id not in visited:
                visit(step_id)

if __name__ == '__main__':
    # Example test
    print("--- Testing Plan Validator ---")
    test_tools = [
        {
            "qualified_name": "filesystem.list_directory",
            "description": "Lists files.",
            "schema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                },
                "required": ["path"]
            }
        },
        {
            "qualified_name": "filesystem.write_file",
            "description": "Writes file.",
            "schema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"}
                },
                "required": ["path", "content"]
            }
        }
    ]
    
    # --- Test 1: Valid Plan ---
    valid_yaml = """
version: 1
vars:
  report_path: "/tmp/report.txt"
steps:
  list:
    tool: filesystem.list_directory
    args:
      path: "."
    save_as: "files"
  
  write:
    tool: filesystem.write_file
    args:
      path: "${vars.report_path}"
      content: "Files: ${steps.list.output}"
    depends_on:
      - "list"
"""
    validator = PlanValidator(test_tools)
    plan, errors = validator.validate(valid_yaml)
    print(f"\nTest 1 (Valid): Errors = {len(errors)}")
    assert len(errors) == 0

    # --- Test 2: Invalid (Missing Dep) ---
    invalid_yaml_1 = """
version: 1
steps:
  write:
    tool: filesystem.write_file
    args:
      path: "out.txt"
      content: "${steps.list.output}"
    depends_on:
      - "list" # 'list' does not exist
"""
    validator = PlanValidator(test_tools)
    plan, errors = validator.validate(invalid_yaml_1)
    print(f"\nTest 2 (Missing Dep): Errors = {len(errors)}")
    for e in errors: print(f"  - {e}")
    assert any("missing dependency 'list'" in e for e in errors)
    
    # --- Test 3: Invalid (Bad Arg) ---
    invalid_yaml_2 = """
version: 1
steps:
  list:
    tool: filesystem.list_directory
    args:
      path: 123 # Should be string
"""
    validator = PlanValidator(test_tools)
    plan, errors = validator.validate(invalid_yaml_2)
    print(f"\nTest 3 (Bad Arg): Errors = {len(errors)}")
    for e in errors: print(f"  - {e}")
    assert any("Arg error at 'path'" in e for e in errors)

    # --- Test 4: Invalid (Unknown Tool) ---
    invalid_yaml_3 = """
version: 1
steps:
  list:
    tool: filesystem.delete_everything
    args: {}
"""
    validator = PlanValidator(test_tools)
    plan, errors = validator.validate(invalid_yaml_3)
    print(f"\nTest 4 (Unknown Tool): Errors = {len(errors)}")
    for e in errors: print(f"  - {e}")
    assert any("not in the list of available tools" in e for e in errors)

    # --- Test 5: Valid (Interpolated Arg) ---
    valid_yaml_2 = """
version: 1
steps:
  list:
    tool: filesystem.list_directory
    args:
      path: "${vars.some_path}" # Interpolated, should be fine
"""
    validator = PlanValidator(test_tools)
    plan, errors = validator.validate(valid_yaml_2)
    print(f"\nTest 5 (Interpolated Arg): Errors = {len(errors)}")
    for e in errors: print(f"  - {e}")
    assert len(errors) == 0
    assert len(validator.warnings) > 0 # Should have a warning
    print(f"  Warnings: {validator.warnings}")