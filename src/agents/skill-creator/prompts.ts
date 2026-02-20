/**
 * Skill Creator Agent Prompts
 *
 * Phase-based prompts for the skill creation process.
 * Migrated from prompt_builder.ts
 */

// ============================================================================
// Phase 1: Tool Selection (Discovery & Reasoning)
// ============================================================================

export const SKILL_CREATOR_PHASE1_SYSTEM = `You are the Skill Creator Orchestrator (Phase 1: Discovery).
Your goal is to select the best tools to build a new SKILL: a reusable orchestration graph over MCP tools.

Rules:
1. Review the GOAL and the AVAILABLE TOOLS (descriptions only).
2. Design an execution graph:
   - nodes = tool calls or compute steps
   - edges = data/control dependencies
   - mark which nodes can run in parallel (think Promise.all / asyncio.gather)
3. Select a minimal set of tools required to achieve the goal.
4. If you lack a necessary tool, describe it in "missing_capabilities".
5. Output a JSON object with:
   - "reasoning": string (why this toolchain + graph works)
   - "selected_tools": string[] (qualified names from context)
   - "execution_graph": object (nodes + edges + parallel_groups)
   - "missing_capabilities": string[] (search queries for missing tools)
   - "questions": string[] (if the goal is ambiguous)

Do not generate code yet. Just plan the toolchain.`;

export interface ToolSelectionResponse {
	reasoning: string;
	selected_tools: string[];
	execution_graph?: {
		nodes: Array<{
			id: string;
			kind: "tool" | "compute";
			name: string;
			note?: string;
		}>;
		edges: Array<{ from: string; to: string; note?: string }>;
		parallel_groups?: Array<{ ids: string[]; note?: string }>;
	};
	missing_capabilities: string[];
	questions: string[];
}

export function buildSelectionPrompt(
	goal: string,
	tools: Array<{ qualifiedName: string; description: string }>,
	constraints: string[],
): { system: string; user: string } {
	const toolList =
		tools.map((t) => `- ${t.qualifiedName}\n  ${t.description}`).join("\n") ||
		"- (none)";
	const constraintList = constraints.length
		? constraints.map((c) => `- ${c}`).join("\n")
		: "- (none)";

	const userPrompt = `GOAL:\n${goal}\n\nCONSTRAINTS:\n${constraintList}\n\nAVAILABLE TOOLS:\n${toolList}\n\nINSTRUCTION:\nSelect the tools needed to build this skill. 
- If you see tools that can fulfill the goal (even partially), include them in 'selected_tools'.
- If tools are missing, list search queries in 'missing_capabilities'.
- You MUST select at least one tool if possible.
Return JSON only.`;

	return { system: SKILL_CREATOR_PHASE1_SYSTEM, user: userPrompt };
}

// ============================================================================
// Phase 2: Skill Generation (Code & Manifest)
// ============================================================================

export const SKILL_CREATOR_PHASE2_SYSTEM = `You are the Skill Creator Orchestrator (Phase 2: Implementation).
You create HIGH-LEVEL SKILLS: reusable orchestrators that solve a task by chaining tools as a graph.

Think of a skill as:
- a mini program (can loop/branch)
- an execution graph over MCP tools
- an abstraction boundary: workflows only see the skill interface + examples, not the underlying tools

Rules:
1. Output a single JSON object.
2. The JSON must include: skill_id, summary, interface, bindings, fanout_tools, code, examples.
   It MAY include: keywords, dependencies.
3. Use ONLY the tools provided in CONTEXT (full schemas included).
4. Use Python 3.10+ with asyncio.
5. Define the skill in 'lib.py'.
6. 'bindings' map short aliases to tool server prefixes (e.g. 'ctx' -> 'context7').
7. 'fanout_tools' must list every tool qualified name called in the code.
8. Graph execution:
   - Use asyncio.gather(...) for independent tool calls (parallel fanout), similar to Promise.all().
   - Sequence calls only when one depends on another.
   - Keep IO through tools, keep compute in Python.
9. Safety:
   - All external side effects MUST go through the provided tools via _bindings.
   - Do NOT use direct file/network/process APIs: open(), requests, aiohttp, httpx, urllib, socket, subprocess, os.system, etc.
10. Interfaces:
    - Provide simple call signatures (e.g. fetch_and_store(library, topic, output_dir)).
    - Do NOT include "async def" or return type annotations in the interface strings.
11. Examples:
    - Provide at least one example showing import skills + await skills.load("<skill-id>").<fn>(...).
    - Examples should be realistic, not placeholder-only.`;

export interface SkillDraftResponse {
	skill_id: string;
	summary: string;
	interface: string[];
	bindings: Record<string, string>;
	fanout_tools: string[];
	code: string;
	examples: Array<{
		title?: string;
		description?: string;
		code: string;
	}>;
	keywords?: string[];
	dependencies?: string[];
	questions?: string[];
}

export function buildGenerationPrompt(
	goal: string,
	selectedTools: Array<{
		qualifiedName: string;
		description: string;
		schema?: unknown;
	}>,
	plan: string,
): { system: string; user: string } {
	const context = selectedTools
		.map((t) => {
			const schema = t.schema
				? JSON.stringify(t.schema, null, 2)
				: "(no schema)";
			return `TOOL: ${t.qualifiedName}\nDESCRIPTION: ${t.description}\nSCHEMA:\n${schema}\n`;
		})
		.join("\n---\n");

	const userPrompt = `GOAL:\n${goal}\n\nPLAN:\n${plan}\n\nCONTEXT (Selected Tools):\n${context}\n\nINSTRUCTION:\nWrite the Python skill code and manifest. Implement the execution graph using asyncio (use asyncio.gather for parallel groups). Return JSON only.`;

	return { system: SKILL_CREATOR_PHASE2_SYSTEM, user: userPrompt };
}

// ============================================================================
// Utilities
// ============================================================================

export const SYSTEM_PROMPT_REPAIR = `You are a JSON repair bot. Fix invalid JSON only.`;

export function buildRepairPrompt(raw: string): {
	system: string;
	user: string;
} {
	const userPrompt = `The following JSON is invalid. Fix it and return only valid JSON.\n\nINVALID:\n${raw}`;
	return { system: SYSTEM_PROMPT_REPAIR, user: userPrompt };
}

// ============================================================================
// Unified Skill Creator Prompt (for single-phase mode)
// ============================================================================

export const SKILL_CREATOR_UNIFIED_SYSTEM = `You are the Skill Creator Orchestrator.
You will iteratively discover tools/skills, inspect schemas, refine a plan, then output a FINAL skill draft.

Skill requirements:
- Skills are higher-level orchestration graphs over MCP tools.
- You may use loops/branching/helpers and asyncio.gather for parallel fanout.
- All external side effects MUST go through provided tools via _bindings.
- Never use raw IO/network/process APIs (open, requests, aiohttp, httpx, urllib, socket, subprocess, os.system, etc.).

When done, return type=final with result matching the skill draft JSON schema:
{
  "skill_id": string,
  "summary": string,
  "interface": string[],
  "bindings": object,
  "fanout_tools": string[],
  "code": string,
  "examples": [{"code": string, "title"?: string, "description"?: string}],
  "dependencies"?: string[]
}`;

export function buildUnifiedPrompt(
	goal: string,
	constraints: string[],
	initialTools: Array<{ qualifiedName: string; description: string }>,
	initialSkills: Array<{ skillRef: string; description: string }>,
): { system: string; user: string } {
	const userPrompt = `GOAL:\n${goal}\n\nCONSTRAINTS:\n${constraints.map((c) => `- ${c}`).join("\n") || "- (none)"}\n\nINITIAL TOOL CANDIDATES (summaries):\n${initialTools.map((t) => `- ${t.qualifiedName}: ${t.description}`).join("\n") || "- (none)"}\n\nRELATED EXISTING SKILLS (summaries):\n${initialSkills.map((s) => `- ${s.skillRef}: ${s.description}`).join("\n") || "- (none)"}\n\nUse capability_search to find more tools/skills and system.load_capability to inspect them. Use update_plan as you refine.`;

	return { system: SKILL_CREATOR_UNIFIED_SYSTEM, user: userPrompt };
}
