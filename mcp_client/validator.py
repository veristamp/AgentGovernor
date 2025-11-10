# mcp_client/validator.py
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, MutableMapping, Sequence, Set

import yaml
import jsonschema  # You must install this: uv pip install jsonschema

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s validator :: %(message)s"
)
log = logging.getLogger("validator")


class WorkflowValidator:
    """
    Performs a "dry run" validation of a workflow YAML file.
    
    Checks for:
    1.  Valid graph structure (missing dependencies, cycles).
    2.  Valid tool arguments against a JSON schema.
    """
    def __init__(self, tools_schema_path: str | Path):
        self.tools_schema = self._load_tools_schema(tools_schema_path)
        self.errors: List[str] = []
        self.warnings: List[str] = []

    def _load_tools_schema(self, schema_path: str | Path) -> Dict[str, Any]:
        """Loads the tools_schema.json file into a map for easy lookup."""
        try:
            with open(schema_path, "r", encoding="utf-8") as f:
                schema_list = json.load(f)
            
            # Convert list to a map of qualified_name -> schema
            schema_map = {}
            for tool in schema_list:
                if "qualified_name" in tool and "schema" in tool:
                    schema_map[tool["qualified_name"]] = tool["schema"]
                else:
                    self.warnings.append(f"Skipping malformed tool entry in schema: {tool.get('qualified_name')}")
            
            log.info("Loaded %d tool schemas from %s", len(schema_map), schema_path)
            return schema_map
        
        except FileNotFoundError:
            log.error("CRITICAL: Tools schema file not found at %s", schema_path)
            sys.exit(1)
        except json.JSONDecodeError:
            log.error("CRITICAL: Could not parse tools schema file at %s. Is it valid JSON?", schema_path)
            sys.exit(1)

    def validate_workflow(self, yaml_path: str | Path) -> bool:
        """Main entrypoint to validate a workflow file."""
        log.info("Starting validation for: %s", yaml_path)
        self.errors = []
        self.warnings = []

        try:
            with open(yaml_path, "r", encoding="utf-8") as f:
                wf = yaml.safe_load(f) or {}
        except FileNotFoundError:
            self.errors.append(f"Workflow file not found: {yaml_path}")
            return self._print_results()
        except yaml.YAMLError as e:
            self.errors.append(f"Error parsing YAML: {e}")
            return self._print_results()

        if not isinstance(wf, Mapping):
            self.errors.append("Workflow file must be a top-level dictionary (map).")
            return self._print_results()

        # --- THIS BLOCK IS UPDATED ---
        steps_data: Any = wf.get("steps") or {}
        if not isinstance(steps_data, Mapping):
            self.errors.append(
                "Workflow 'steps' key must be a dictionary (a map) of step IDs. "
                "Found a list instead. Are you using the old sequential YAML format?"
            )
            return self._print_results()
        
        steps: Dict[str, Any] = dict(steps_data)
        # --- END OF UPDATE ---
        
        if not steps:
            self.warnings.append("Workflow has no 'steps' defined.")
            return self._print_results()

        # 1. Validate Graph Structure
        self._validate_graph(steps)

        # 2. Validate Step Schemas (Tools, Logic, etc.)
        self._validate_all_steps(steps)
        
        return self._print_results()

    def _print_results(self) -> bool:
        """Prints all collected errors and warnings."""
        if not self.errors and not self.warnings:
            log.info("--- VALIDATION SUCCESSFUL ---")
            log.info("Workflow graph is well-formed and all tool arguments are valid.")
            return True
        
        if self.warnings:
            log.warning("--- VALIDATION COMPLETED WITH WARNINGS ---")
            for warning in self.warnings:
                log.warning("  - %s", warning)

        if self.errors:
            log.error("--- VALIDATION FAILED ---")
            for error in self.errors:
                log.error("  - %s", error)
            return False
        
        return True # Warnings only

    def _validate_graph(self, steps: Dict[str, Any]):
        """Checks for missing dependencies and cycles."""
        all_step_ids = set(steps.keys())
        
        # Check for missing dependencies
        for step_id, config in steps.items():
            deps = config.get("depends_on", [])
            for dep_id in deps:
                if dep_id not in all_step_ids:
                    self.errors.append(f"Step '{step_id}' has a missing dependency: '{dep_id}'")

        # Check for cycles using Depth First Search (DFS)
        path: Set[str] = set()
        visited: Set[str] = set()

        def visit(step_id: str):
            path.add(step_id)
            for dep_id in steps[step_id].get("depends_on", []):
                if dep_id not in all_step_ids:
                    continue # Already caught by missing dep check
                if dep_id in path:
                    cycle = " -> ".join(list(path) + [dep_id])
                    self.errors.append(f"Circular dependency (cycle) detected: {cycle}")
                    return
                if dep_id not in visited:
                    visit(dep_id)
            path.remove(step_id)
            visited.add(step_id)

        for step_id in all_step_ids:
            if step_id not in visited:
                visit(step_id)
        
    def _validate_all_steps(self, steps: Dict[str, Any]):
        """Iterates all steps and validates their individual schemas."""
        for step_id, config in steps.items():
            self.validate_step_config(step_id, config, set(steps.keys()))

    def validate_step_config(self, step_id: str, config: Dict[str, Any], all_step_ids: Set[str], is_nested: bool = False):
        """
        Validates a single step config, recursing for if/loop.
        `is_nested` refers to steps inside an if/loop.
        """
        
        # --- Validate Tool Step ---
        if "tool" in config:
            tool_name = config["tool"]
            if not isinstance(tool_name, str):
                self.errors.append(f"Step '{step_id}': 'tool' name must be a string, got {type(tool_name)}")
                return

            # Check if interpolation is used for tool name. This is a common error.
            if "${" in tool_name:
                self.errors.append(f"Step '{step_id}': 'tool' name cannot be dynamic (contains '${{...}}'). Found: {tool_name}")
                return

            if tool_name not in self.tools_schema:
                self.errors.append(f"Step '{step_id}': Tool '{tool_name}' not found in tools schema.")
                return

            tool_schema = self.tools_schema[tool_name]
            tool_args = config.get("args", {})

            if not isinstance(tool_args, dict):
                self.errors.append(f"Step '{step_id}': 'args' must be a dictionary (map), got {type(tool_args)}")
                return
            
            # We validate the *un-interpolated* args.
            # This checks:
            #   1. All 'required' properties are present.
            #   2. The *type* of any literal values is correct.
            #   (e.g., path: 123 instead of path: "abc")
            try:
                # We can't validate interpolated values, so we create a custom
                # validator that "ignores" type errors if the value is a string
                # that looks like an interpolation.
                validator = jsonschema.Draft7Validator(tool_schema)
                
                for error in sorted(validator.iter_errors(tool_args), key=str):
                    # Don't flag type errors for string values that are interpolations
                    is_interpolation = isinstance(error.instance, str) and error.instance.startswith("${")
                    
                    if error.validator == "type" and is_interpolation:
                        # It's an interpolation string, but schema expected e.g. number.
                        # We can't validate this statically. Add a warning.
                        self.warnings.append(f"Step '{step_id}': Arg '{'.'.join(error.path)}' is a dynamic value ('{error.instance}'). Type validation skipped.")
                    else:
                        self.errors.append(f"Step '{step_id}' (Tool: {tool_name}): Argument error at '{'.'.join(error.path)}' - {error.message}")
                        
            except jsonschema.SchemaError as e:
                self.errors.append(f"Step '{step_id}': Internal Schema Error for {tool_name}: {e}")

        # --- Validate Logic Steps (Recursive) ---
        elif "if" in config:
            if "then" in config and isinstance(config["then"], list):
                self._validate_sequential_list(f"{step_id}.then", config["then"], all_step_ids)
            if "else" in config and isinstance(config["else"], list):
                self._validate_sequential_list(f"{step_id}.else", config["else"], all_step_ids)

        elif "loop" in config:
            if "do" in config and isinstance(config["do"], list):
                self._validate_sequential_list(f"{step_id}.do", config["do"], all_step_ids)

        elif "set" in config:
            if not isinstance(config["set"], dict) or "var" not in config["set"]:
                self.errors.append(f"Step '{step_id}': 'set' step is malformed. Expected '{{set: {{var: name, value: ...}}}}'")

        elif "log" in config:
            pass # 'log' steps are generally free-form
        
        elif not is_nested:
            # Only raise if it's not a step inside a list (like if/loop)
            self.errors.append(f"Step '{step_id}': Unknown step type. Must contain 'tool', 'if', 'loop', 'set', or 'log'.")

    def _validate_sequential_list(self, context: str, steps_list: List[Any], all_step_ids: Set[str]):
        """Validates steps inside a sequential list (like if/loop)."""
        if not isinstance(steps_list, list):
             self.errors.append(f"Context '{context}': Expected a list of steps, got {type(steps_list)}")
             return

        for i, step in enumerate(steps_list):
            step_id = f"{context}[{i}]"
            if not isinstance(step, dict):
                self.errors.append(f"Step '{step_id}': Step in a sequential list must be a dictionary (map).")
                continue
            
            # Nested steps can't have 'depends_on'
            if "depends_on" in step:
                 self.errors.append(f"Step '{step_id}': 'depends_on' is not allowed inside a sequential 'if' or 'loop' block.")

            # Recurse
            self.validate_step_config(step_id, step, all_step_ids, is_nested=True)


def main():
    """Entrypoint for the validator script."""
    p = argparse.ArgumentParser(
        description="Dry-run validator for MCP workflow YAML files.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    p.add_argument(
        "yaml_path",
        help="Path to the workflow YAML file to validate."
    )
    p.add_argument(
        "--schema-path",
        default="tools_schema.json",
        help="Path to the tools_schema.json file."
    )
    args = p.parse_args()

    # Find schema relative to this script, if default is used
    if args.schema_path == "tools_schema.json":
        # Check in CWD
        local_schema = Path("tools_schema.json")
        # Check relative to script
        script_dir_schema = Path(__file__).parent.parent / "tools_schema.json"
        
        if local_schema.exists():
            schema_path = local_schema.resolve()
        elif script_dir_schema.exists():
            schema_path = script_dir_schema.resolve()
        else:
            log.error("CRITICAL: Cannot find 'tools_schema.json' in current directory or project root.")
            sys.exit(1)
    else:
        schema_path = Path(args.schema_path)

    validator = WorkflowValidator(schema_path)
    is_valid = validator.validate_workflow(Path(args.yaml_path))

    if not is_valid:
        sys.exit(1)


if __name__ == "__main__":
    main()