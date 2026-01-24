import type { SkillCreatorSession, ToolDescriptor } from './types';

// ============================================================================
// Phase 1: Tool Selection (Discovery & Reasoning)
// ============================================================================

const SYSTEM_PROMPT_SELECTION = `You are the Skill Creator Orchestrator (Phase 1: Discovery).
Your goal is to select the best tools to build a new skill.

Rules:
1. Review the GOAL and the AVAILABLE TOOLS (descriptions only).
2. Think step-by-step about what logic is needed.
3. Select a minimal set of tools required to achieve the goal.
4. If you lack a necessary tool, describe it in "missing_capabilities".
5. Output a JSON object with:
   - "reasoning": string (explanation of your plan)
   - "selected_tools": string[] (list of qualified names from context)
   - "missing_capabilities": string[] (search queries for missing tools)
   - "questions": string[] (if the goal is ambiguous)

Do not generate code yet. Just plan the toolchain.`;

export interface ToolSelectionResponse {
    reasoning: string;
    selected_tools: string[];
    missing_capabilities: string[];
    questions: string[];
}

function formatToolSummary(tool: ToolDescriptor): string {
    // Description is now clean from the DB/JSON, no manual truncation needed.
    return `- ${tool.qualifiedName}\n  ${tool.description}`;
}

export function buildSelectionPrompt(goal: string, tools: ToolDescriptor[], constraints: string[]): { system: string; user: string } {
    const toolList = tools.map(formatToolSummary).join('\n') || '- (none)';
    const constraintList = constraints.length ? constraints.map((c) => `- ${c}`).join('\n') : '- (none)';

    const userPrompt = `GOAL:\n${goal}\n\nCONSTRAINTS:\n${constraintList}\n\nAVAILABLE TOOLS:\n${toolList}\n\nINSTRUCTION:\nSelect the tools needed to build this skill. \n- If you see tools that can fulfill the goal (even partially), include them in 'selected_tools'.\n- If tools are missing, list search queries in 'missing_capabilities'.\n- You MUST select at least one tool if possible.\nReturn JSON only.`;

    return { system: SYSTEM_PROMPT_SELECTION, user: userPrompt };
}

// ============================================================================
// Phase 2: Skill Generation (Code & Manifest)
// ============================================================================

const SYSTEM_PROMPT_GENERATION = `You are the Skill Creator Orchestrator (Phase 2: Implementation).
You design governed skills using the selected tools.

Rules:
1. Output a single JSON object.
2. The JSON must include: skill_id, summary, interface, bindings, fanout_tools, code.
3. Use ONLY the tools provided in CONTEXT (full schemas included).
4. Use Python 3.10+ with asyncio.
5. Define the skill in 'lib.py'.
6. 'bindings' map short aliases to tool server prefixes (e.g. 'ctx' -> 'context7').
7. 'fanout_tools' must list every tool qualified name called in the code.
8. Interfaces should be simple Python function signatures.
`;

export interface SkillDraftResponse {
    skill_id: string;
    summary: string;
    interface: string[];
    bindings: Record<string, string>;
    fanout_tools: string[];
    code: string;
    questions?: string[]; // Legacy compatibility
}

function formatToolSchema(tool: ToolDescriptor): string {
    const schema = tool.schema ? JSON.stringify(tool.schema, null, 2) : '(no schema)';
    return `TOOL: ${tool.qualifiedName}\nDESCRIPTION: ${tool.description}\nSCHEMA:\n${schema}\n`;
}

export function buildGenerationPrompt(goal: string, selectedTools: ToolDescriptor[], plan: string): { system: string; user: string } {
    const context = selectedTools.map(formatToolSchema).join('\n---\n');
    
    const userPrompt = `GOAL:\n${goal}\n\nPLAN:\n${plan}\n\nCONTEXT (Selected Tools):\n${context}\n\nINSTRUCTION:\nWrite the Python skill code and manifest. Return JSON only.`;

    return { system: SYSTEM_PROMPT_GENERATION, user: userPrompt };
}

// ============================================================================
// Utilities
// ============================================================================

export const SYSTEM_PROMPT_REPAIR = `You are a JSON repair bot. Fix invalid JSON only.`;

export function buildRepairPrompt(raw: string): { system: string; user: string } {
    const userPrompt = `The following JSON is invalid. Fix it and return only valid JSON.\n\nINVALID:\n${raw}`;
    return { system: SYSTEM_PROMPT_REPAIR, user: userPrompt };
}
