#!/usr/bin/env python3
"""
Main entrypoint for the MCP Agent Planner.

Supports two modes:
1. YAML Mode (legacy): Generates YAML workflows for workflow_executor.py
2. Code Mode (new): Generates Python code for sandbox execution

This script orchestrates the modular components to:
1. Check for matching skills (Code Mode first)
2. Decompose a user goal into RAG sub-queries.
3. Retrieve relevant tools from Qdrant using diversified RAG.
4. Build a prompt (YAML or Code depending on mode).
5. Get a plan from a local LLM.
6. Validate the plan (YAML validator or Code auditor).
7. Run a repair loop.
8. Return the final validated plan.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import yaml
from typing import Any, Dict, List, Optional, Tuple

# --- Import modular components ---
from Agent import config
from Agent.tool_retriever import find_relevant_tools
from Agent.prompt_builder import build_planner_prompt, _format_tools_for_context
from Agent.llm_client import get_llm_completion, extract_yaml_block
from Agent.plan_validator import PlanValidator

# NEW: Code Mode imports
from Agent.skill_retriever import find_relevant_skill, get_skill_bindings
from Agent.code_prompt_builder import (
    build_code_prompt,
    build_repair_prompt,
    extract_code_from_response,
    SYSTEM_PROMPT_CODE,
    SYSTEM_PROMPT_CODE_REPAIR
)
from Agent.code_auditor import CodeAuditor, AuditResult

# --- Setup Logging ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s planner :: %(message)s"
)
log = logging.getLogger("planner")

# --- System Prompts ---
SYSTEM_PROMPT_PLAN = "You are The Orchestrator. Your job is to compile a user GOAL into a deterministic YAML workflow plan. You never execute code or explain reasoning; you *only* emit a single, valid YAML code block."
SYSTEM_PROMPT_REPAIR = "You are a YAML auto-correcting bot. A user will provide a broken YAML plan and a list of errors. Your *only* job is to fix the YAML and return a single, corrected YAML code block. Do not add any explanation."

# NEW System Prompt for RAG query decomposition
SYSTEM_PROMPT_DECOMPOSE = """
You are a RAG query expansion bot. Your job is to
decompose a user's goal into a JSON list of 3-5
distinct sub-queries. These queries will be used to
search for tools from different servers.

Focus on the *actions* or *domains* in the goal.
For example:
Goal: "List files, save them to memory, and run a command"
Output:
["list files in directory", "save content to knowledge graph", "run a terminal command"]

Goal: "Analyze the mcp_client folder tree and get the code for _execute_single_step"
Output:
["get folder tree structure", "get code for a function", "analyze code"]

Return *only* the JSON list.
"""

# NEW System Prompt for RAG self-correction
SYSTEM_PROMPT_EXPAND_QUERY = """
You are a RAG query expansion bot. A previous attempt
to find tools for a user's goal failed because some
tools were missing. The user's goal, the tools that
were found, and the errors are provided.

Your job is to generate a new, better search
query to find the *missing* tools.

Return *only* the new search query as a single string.
"""


def run_code_planner_loop(goal: str, verbose: bool = False) -> Optional[Tuple[str, Dict[str, Any]]]:
    """
    Runs the Code Mode planner loop.
    
    Returns:
        Tuple of (code_string, manifest_dict) on success, None on failure.
    """
    log.info("=== GOVERNED CODE MODE ===")
    
    # --- 1. Check for matching skill ---
    log.info("Step 1: Searching for matching skill...")
    skill, skill_score = find_relevant_skill(goal)
    
    if skill:
        log.info(f"✅ SKILL HIT: {skill.name} (score: {skill_score:.4f})")
        log.info(f"   Description: {skill.description[:100]}...")
        log.info(f"   Bindings: {skill.bindings}")
    else:
        log.info("No matching skill found. Using tool retrieval.")
    
    # --- 2. Decompose Goal for RAG ---
    log.info("Step 2: Decomposing goal for diversified RAG...")
    decompose_prompt = f'GOAL: "{goal}"'
    llm_response = get_llm_completion(SYSTEM_PROMPT_DECOMPOSE, decompose_prompt)
    
    try:
        sub_queries = json.loads(llm_response)
        if not isinstance(sub_queries, list) or not sub_queries:
            raise ValueError("LLM did not return a valid list")
        if goal not in sub_queries:
            sub_queries.insert(0, goal)
        log.info(f"   Decomposed into: {sub_queries}")
    except Exception as e:
        log.warning(f"   Failed to decompose goal: {e}. Using original goal.")
        sub_queries = [goal]
    
    # --- 3. Retrieve Tools ---
    log.info("Step 3: Retrieving tools from RAG...")
    try:
        retrieved_tools = find_relevant_tools(sub_queries, top_k=config.DEFAULT_TOOL_TOP_K)
    except Exception as e:
        log.critical(f"Failed to retrieve tools: {e}")
        return None
    
    if not retrieved_tools:
        log.error("No relevant tools found. Cannot create a plan.")
        return None
    
    log.info(f"   Found {len(retrieved_tools)} tools")
    
    # If we have a skill, filter tools to only the ones the skill uses
    if skill and skill.bindings:
        skill_binding_set = set(skill.bindings)
        skill_tools = [t for t in retrieved_tools if t.get('qualified_name') in skill_binding_set]
        if skill_tools:
            log.info(f"   Filtered to {len(skill_tools)} tools matching skill bindings")
            retrieved_tools = skill_tools
    
    # --- 4. Build Code Prompt ---
    log.info("Step 4: Building code generation prompt...")
    user_prompt = build_code_prompt(goal, retrieved_tools, skill=skill)
    
    if verbose:
        log.info(f"\n--- CODE PROMPT (first 1500 chars) ---\n{user_prompt[:1500]}...\n")
    
    # --- 5. Generate Code ---
    log.info("Step 5: Requesting code from LLM...")
    llm_response = get_llm_completion(SYSTEM_PROMPT_CODE, user_prompt)
    
    if llm_response.startswith("Error:"):
        log.critical(f"LLM call failed: {llm_response}")
        return None
    
    code = extract_code_from_response(llm_response)
    
    if not code:
        log.error("Failed to extract Python code from LLM response")
        log.debug(f"Raw response: {llm_response[:500]}...")
        return None
    
    if verbose:
        log.info(f"\n--- LLM CODE DRAFT ---\n{code}\n")
    
    # --- 6. Audit & Repair Loop ---
    auditor = CodeAuditor()
    available_bindings = {t.get('qualified_name') for t in retrieved_tools if t.get('qualified_name')}
    
    for attempt in range(1, config.MAX_REPAIR_ITERATIONS + 1):
        log.info(f"Step 6: Audit attempt {attempt}/{config.MAX_REPAIR_ITERATIONS}...")
        
        result = auditor.audit(code, available_bindings)
        
        if result.is_valid:
            log.info("✅ Code passed audit!")
            manifest = result.manifest.to_dict() if result.manifest else {}
            log.info(f"   Manifest: {manifest}")
            return (code, manifest)
        
        # --- Audit Failed ---
        log.warning(f"   Code failed audit with {len(result.errors)} errors:")
        for e in result.errors:
            log.warning(f"     - {e}")
        
        if result.warnings:
            for w in result.warnings:
                log.info(f"     ⚠ {w}")
        
        if attempt == config.MAX_REPAIR_ITERATIONS:
            log.error("Max repair iterations reached. Failed to generate valid code.")
            break
        
        # --- Repair ---
        log.info("   Requesting LLM to repair the code...")
        repair_prompt = build_repair_prompt(code, result.errors, goal)
        llm_response = get_llm_completion(SYSTEM_PROMPT_CODE_REPAIR, repair_prompt)
        
        if llm_response.startswith("Error:"):
            log.critical(f"LLM repair call failed: {llm_response}")
            break
        
        code = extract_code_from_response(llm_response)
        
        if not code:
            log.error("Failed to extract repaired code from LLM response")
            break
        
        if verbose:
            log.info(f"\n--- LLM REPAIR DRAFT ---\n{code}\n")
    
    return None


def run_planner_loop(goal: str, verbose: bool = False) -> Optional[Dict[str, Any]]:
    """
    Runs the full Goal -> RAG -> LLM -> Validate -> Repair loop (YAML mode).
    Returns the final parsed plan on success, None on failure.
    """
    
    # --- 1. Decompose Goal for RAG ---
    log.info(f"Decomposing goal for diversified RAG: '{goal}'")
    decompose_prompt = f'GOAL: "{goal}"'
    llm_response = get_llm_completion(SYSTEM_PROMPT_DECOMPOSE, decompose_prompt)
    
    try:
        sub_queries = json.loads(llm_response)
        if not isinstance(sub_queries, list) or not sub_queries:
            raise ValueError("LLM did not return a valid list")
        if goal not in sub_queries:
            sub_queries.insert(0, goal)
        log.info(f"Decomposed into sub-queries: {sub_queries}")
    except Exception as e:
        log.warning(f"Failed to decompose goal: {e}. Falling back to original goal.")
        sub_queries = [goal]

    # --- 2. RAG: Retrieve Tools ---
    log.info(f"Retrieving tools for {len(sub_queries)} queries...")
    try:
        retrieved_tools = find_relevant_tools(sub_queries, top_k=config.DEFAULT_TOOL_TOP_K)
    except Exception as e:
        log.critical(f"Failed to retrieve tools: {e}")
        return None
        
    if not retrieved_tools:
        log.error("No relevant tools were found for this goal. Cannot create a plan.")
        return None
    
    # --- 3. Build Initial Prompt ---
    log.info(f"Building RICECO prompt with {len(retrieved_tools)} tools.")
    user_prompt = build_planner_prompt(goal, retrieved_tools)
    
    if verbose:
        log.info(f"\n--- RICECO PROMPT (first 1000 chars) ---\n{user_prompt[:1000]}...\n")

    # --- 4. Initial LLM Call ---
    log.info("Sending initial plan request to LLM...")
    llm_response = get_llm_completion(SYSTEM_PROMPT_PLAN, user_prompt)
    
    if llm_response.startswith("Error:"):
        log.critical(f"LLM call failed: {llm_response}")
        return None
        
    yaml_block = extract_yaml_block(llm_response)
    
    if verbose:
        log.info(f"\n--- LLM DRAFT ---\n{yaml_block}\n")

    # --- 5. Validation & Repair Loop ---
    current_plan: Optional[Dict[str, Any]] = None
    
    for attempt in range(1, config.MAX_REPAIR_ITERATIONS + 1):
        log.info(f"Validation attempt {attempt}/{config.MAX_REPAIR_ITERATIONS}...")
        
        # --- 5a. Validate ---
        validator = PlanValidator(retrieved_tools)
        parsed_plan, errors = validator.validate(yaml_block)
        
        if not errors:
            log.info("✅ Plan is valid!")
            current_plan = parsed_plan
            break
        
        # --- 5b. Validation Failed ---
        log.warning(f"Plan failed validation with {len(errors)} errors:")
        for e in errors:
            log.warning(f"  - {e}")
        
        if attempt == config.MAX_REPAIR_ITERATIONS:
            log.error("Max repair iterations reached. Failed to generate a valid plan.")
            break
            
        # --- 5c. RAG Self-Correction ---
        is_rag_failure = any("not in the list of available tools" in e for e in errors)

        if is_rag_failure:
            log.warning("RAG FAILURE detected. Attempting to expand query...")
            
            expand_prompt = f"""
ORIGINAL GOAL: "{goal}"

TOOLS WE ALREADY FOUND (Do not search for these):
{_format_tools_for_context(retrieved_tools)}

VALIDATION ERRORS (What's missing):
{chr(10).join(f'- {e}' for e in errors)}

Please generate a new query to find the missing tools.
"""
            new_query = get_llm_completion(SYSTEM_PROMPT_EXPAND_QUERY, expand_prompt).strip()
            
            if new_query.startswith("Error:") or not new_query:
                 log.error(f"LLM failed to generate expansion query. Aborting.")
                 break

            log.info(f"LLM generated new query: '{new_query}'")
            
            # --- Re-run RAG with the new query ---
            log.info("Re-running RAG with expanded query...")
            try:
                new_tools = find_relevant_tools([new_query])
                
                existing_tool_names = {t['qualified_name'] for t in retrieved_tools}
                added_count = 0
                for tool in new_tools:
                    if tool['qualified_name'] not in existing_tool_names:
                        retrieved_tools.append(tool)
                        added_count += 1
                
                if added_count == 0:
                    log.error("RAG self-correction found no new tools. Aborting repair.")
                    break
                
                log.info(f"Added {added_count} new tools. RAG context now contains {len(retrieved_tools)} tools.")

                # --- Re-build the *original* planner prompt ---
                log.info("Re-building RICECO prompt with new tools...")
                user_prompt = build_planner_prompt(goal, retrieved_tools)
                
                # Add failure context
                user_prompt += f"""
---
PREVIOUS ATTEMPT FAILED.
Do not make the same mistakes.

ERRORS:
{chr(10).join(f'- {e}' for e in errors)}

FAILED YAML:
```yaml
{yaml_block}
```
---
"""
                
                # --- Re-run the *original* planner ---
                llm_response = get_llm_completion(SYSTEM_PROMPT_PLAN, user_prompt)
                yaml_block = extract_yaml_block(llm_response)
                
                continue
                
            except Exception as e:
                log.error(f"Failed during RAG-repair loop: {e}")
        
        # --- 5d. Standard Syntax Repair ---
        log.info("Requesting LLM to repair the plan (standard syntax repair)...")
        repair_prompt = f"""
The following YAML plan is invalid.

ERRORS:
{chr(10).join(f'- {e}' for e in errors)}

INVALID YAML:
```yaml
{yaml_block}
```

Please fix the YAML and return *only* the corrected code block.
"""
        llm_response = get_llm_completion(SYSTEM_PROMPT_REPAIR, repair_prompt)
        
        if llm_response.startswith("Error:"):
            log.critical(f"LLM repair call failed: {llm_response}")
            break

        yaml_block = extract_yaml_block(llm_response)
        
        if verbose:
            log.info(f"\n--- LLM REPAIR DRAFT ---\n{yaml_block}\n")

    return current_plan


def main():
    """CLI Entrypoint."""
    parser = argparse.ArgumentParser(
        description="MCP Agent Planner: Goal -> Validated Plan (YAML or Code)",
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
        "--code", "--code-mode",
        action="store_true",
        dest="code_mode",
        help="Use Governed Code Mode (Python) instead of YAML mode."
    )
    args = parser.parse_args()

    if not config.LLM_MODEL_NAME or config.LLM_MODEL_NAME == "your-local-model-name":
        log.critical("Error: LLM_MODEL_NAME is not set in Agent/config.py")
        log.critical("Please set it to the model you are serving via LM Studio (or equivalent).")
        sys.exit(1)

    if args.code_mode:
        # --- CODE MODE ---
        result = run_code_planner_loop(args.goal, args.verbose)
        
        if result:
            code, manifest = result
            log.info("--- ✅ FINAL VALIDATED CODE ---")
            print("\n# === MANIFEST ===")
            print(f"# {json.dumps(manifest)}")
            print("\n# === CODE ===")
            print(code)
            sys.exit(0)
        else:
            log.critical("--- ❌ FAILED TO GENERATE VALID CODE ---")
            sys.exit(1)
    else:
        # --- YAML MODE (legacy) ---
        final_plan = run_planner_loop(args.goal, args.verbose)
        
        if final_plan:
            log.info("--- ✅ FINAL VALIDATED PLAN ---")
            print(yaml.safe_dump(final_plan, sort_keys=False, default_flow_style=False))
            sys.exit(0)
        else:
            log.critical("--- ❌ FAILED TO GENERATE A VALID PLAN ---")
            sys.exit(1)


if __name__ == "__main__":
    main()