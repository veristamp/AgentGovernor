#!/usr/bin/env python3
"""
Main entrypoint for the AMCP Agent Planner.

This script orchestrates the modular components to:
1. Get a user goal.
2. Retrieve relevant tools from Qdrant.
3. Build a RICECO prompt.
4. Get a YAML plan from a local LLM.
5. Validate the plan.
6. Run a repair loop if validation fails.
7. Prompt the user to confirm execution.
8. Execute the plan.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import yaml
from typing import Any, Dict, List, Optional

# --- Import modular components ---
from Agent import config
from Agent.tool_retriever import find_relevant_tools
from Agent.prompt_builder import build_planner_prompt
from Agent.llm_client import get_llm_completion, extract_yaml_block
from Agent.plan_validator import PlanValidator

# --- Import Execution Components ---
from mcp_client.manager import MCPClientManager
# Alias MCP's Config to avoid name collision with Agent.config
from mcp_client.config import Config as MCPConfig
from mcp_client.workflow_executor import run_workflow_graph

# --- Setup Logging ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s planner :: %(message)s"
)
log = logging.getLogger("planner")

# --- System Prompts ---
SYSTEM_PROMPT_PLAN = "You are The Orchestrator. Your job is to compile a user GOAL into a deterministic YAML workflow plan. You never execute code or explain reasoning; you *only* emit a single, valid YAML code block."
SYSTEM_PROMPT_REPAIR = "You are a YAML auto-correcting bot. A user will provide a broken YAML plan and a list of errors. Your *only* job is to fix the YAML and return a single, corrected YAML code block. Do not add any explanation."

def run_planner_loop(goal: str, verbose: bool = False) -> Optional[Dict[str, Any]]:
    """
    Runs the full Goal -> RAG -> LLM -> Validate -> Repair loop.
    Returns the final parsed plan on success, None on failure.
    """
    
    # --- 1. RAG: Retrieve Tools ---
    log.info(f"Retrieving tools for goal: '{goal}'")
    try:
        retrieved_tools = find_relevant_tools(goal, top_k=config.DEFAULT_TOOL_TOP_K)
    except Exception as e:
        log.critical(f"Failed to retrieve tools: {e}")
        return None
        
    if not retrieved_tools:
        log.error("No relevant tools were found for this goal. Cannot create a plan.")
        return None
    
    # --- 2. Build Initial Prompt ---
    log.info(f"Building RICECO prompt with {len(retrieved_tools)} tools.")
    user_prompt = build_planner_prompt(goal, retrieved_tools)
    
    if verbose:
        log.info(f"\n--- RICECO PROMPT (first 1000 chars) ---\n{user_prompt[:1000]}...\n")

    # --- 3. Initial LLM Call ---
    log.info("Sending initial plan request to LLM...")
    llm_response = get_llm_completion(SYSTEM_PROMPT_PLAN, user_prompt)
    
    if llm_response.startswith("Error:"):
        log.critical(f"LLM call failed: {llm_response}")
        return None
        
    yaml_block = extract_yaml_block(llm_response)
    
    if verbose:
        log.info(f"\n--- LLM DRAFT ---\n{yaml_block}\n")

    # --- 4. Validation & Repair Loop ---
    current_plan: Optional[Dict[str, Any]] = None
    
    for attempt in range(1, config.MAX_REPAIR_ITERATIONS + 1):
        log.info(f"Validation attempt {attempt}/{config.MAX_REPAIR_ITERATIONS}...")
        
        # --- 4a. Validate ---
        # We must re-create the validator on each loop
        # because the available tools are fixed for *this* run.
        validator = PlanValidator(retrieved_tools)
        parsed_plan, errors = validator.validate(yaml_block)
        
        if not errors:
            log.info("✅ Plan is valid!")
            current_plan = parsed_plan
            break # Success!
        
        # --- 4b. Validation Failed ---
        log.warning(f"Plan failed validation with {len(errors)} errors:")
        for e in errors:
            log.warning(f"  - {e}")
        
        if attempt == config.MAX_REPAIR_ITERATIONS:
            log.error("Max repair iterations reached. Failed to generate a valid plan.")
            break
            
        # --- 4c. Repair ---
        log.info("Requesting LLM to repair the plan...")
        repair_prompt = f"""
The following YAML plan is invalid.

ERRORS:
{'\n'.join(f'- {e}' for e in errors)}

INVALID YAML:
```yaml
{yaml_block}
```

Please fix the YAML and return *only* the corrected code block.
"""
        llm_response = get_llm_completion(SYSTEM_PROMPT_REPAIR, repair_prompt)
        
        if llm_response.startswith("Error:"):
            log.critical(f"LLM repair call failed: {llm_response}")
            break # Abort loop if repair call fails

        yaml_block = extract_yaml_block(llm_response)
        
        if verbose:
            log.info(f"\n--- LLM REPAIR DRAFT ---\n{yaml_block}\n")

    # --- 5. Return Final Result ---
    return current_plan

async def execute_plan(plan: Dict[str, Any]):
    """
    Connects to MCP servers and executes the given plan.
    """
    log.info("--- EXECUTING PLAN ---")
    
    # 1. Set up global vars (as expected by run_workflow_graph)
    global_vars: Dict[str, Any] = {
        "vars": dict(plan.get("vars") or {}),
        "env": dict(os.environ),
        "steps": {} 
    }
    
    # 2. Load MCP servers & connect
    log.info("Loading MCP server configuration from mcp_servers.json...")
    cfg = MCPConfig.load("mcp_servers.json") 
    if not cfg.mcp_servers:
        log.warning("No MCP servers found in mcp_servers.json. Execution may fail.")

    async with MCPClientManager(cfg) as mgr:
        await mgr.wait_ready()
        log.info("MCP Client Manager connected and ready.")
        
        steps: Dict[str, Dict[str, Any]] = dict(plan.get("steps") or {})
        if not steps:
            log.error("No steps found in the plan. Nothing to execute.")
            return

        # 3. Call the imported executor
        await run_workflow_graph(mgr, steps, global_vars)
    
    log.info("--- ✅ PLAN EXECUTION COMPLETE ---")
    
    # 4. Print final state
    final_steps_output = global_vars.get("steps", {})
    log.info("Final step outputs (JSON):")
    try:
        print(json.dumps(final_steps_output, indent=2, default=str))
    except Exception as e:
        log.error(f"Could not serialize final step outputs: {e}")
        print(final_steps_output)

def main():
    """CLI Entrypoint."""
    parser = argparse.ArgumentParser(
        description="AMCP Agent Planner: Goal -> Validated YAML -> Execution",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        "--goal", 
        required=True, 
        help="The natural language goal for the agent."
    )
    parser.add_argument(
        "-v", "--verbose", 
        action="store_true", 
        help="Print full prompts and LLM responses."
    )
    parser.add_argument(
        "-y", "--yes",
        action="store_true",
        help="Automatically confirm and execute the plan without prompting."
    )
    args = parser.parse_args()

    if not config.LLM_MODEL_NAME or config.LLM_MODEL_NAME == "your-local-model-name":
        log.critical("Error: LLM_MODEL_NAME is not set in Agent/config.py")
        log.critical("Please set it to the model you are serving via LM Studio (or equivalent).")
        sys.exit(1)

    # --- PLAN ---
    final_plan = run_planner_loop(args.goal, args.verbose)
    
    if final_plan:
        log.info("--- ✅ FINAL VALIDATED PLAN ---")
        plan_yaml = yaml.safe_dump(final_plan, sort_keys=False, default_flow_style=False)
        print(plan_yaml)
        
        # --- CONFIRM ---
        try:
            if not args.yes:
                input("Press [Enter] to execute this plan, or [Ctrl+C] to cancel...")
        except KeyboardInterrupt:
            log.info("\nExecution cancelled by user.")
            sys.exit(0)
        
        # --- EXECUTE ---
        try:
            asyncio.run(execute_plan(final_plan))
            sys.exit(0)
        except Exception as e:
            log.critical("--- ❌ PLAN EXECUTION FAILED ---")
            log.critical(f"Error: {e}", exc_info=True)
            sys.exit(1)

    else:
        log.critical("--- ❌ FAILED TO GENERATE A VALID PLAN ---")
        sys.exit(1)

if __name__ == "__main__":
    main()