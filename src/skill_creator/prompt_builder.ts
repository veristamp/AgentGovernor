import type { SkillCreatorSession, ToolDescriptor } from './types';

const SYSTEM_PROMPT = `You are the Skill Creator Orchestrator.
You design governed skills from the available tools.

Rules:
1. Output a single JSON object and nothing else.
2. The JSON must include: skill_id, summary, interface, bindings, fanout_tools, code, questions.
3. Use only the tools listed in CONTEXT.
4. Use Python and define the skill in lib.py with async functions.
5. Bindings must map short aliases to tool servers (e.g., ctx -> context7).
6. fanout_tools must include every tool you call.
7. If tools are insufficient, add a question asking for more detail.`;

export interface SkillDraftResponse {
    skill_id: string;
    summary: string;
    interface: string[];
    bindings: Record<string, string>;
    fanout_tools: string[];
    code: string;
    questions: string[];
}

function formatTool(tool: ToolDescriptor): string {
    const schema = tool.schema ? JSON.stringify(tool.schema) : '';
    return [
        `- ${tool.qualifiedName}`,
        `  description: ${tool.description}`,
        schema ? `  schema: ${schema}` : '',
    ]
        .filter(Boolean)
        .join('\n');
}

export function buildPrompt(goal: string, session: SkillCreatorSession): { system: string; user: string } {
    const tools = session.selectedTools.map(formatTool).join('\n\n') || '- (none)';
    const constraints = session.constraints.length ? session.constraints.map((line) => `- ${line}`).join('\n') : '- (none)';
    const questions = session.questions.length ? session.questions.map((line) => `- ${line}`).join('\n') : '- (none)';

    const userPrompt = `ROLE:\nYou are the Skill Creator Orchestrator.\n\nINSTRUCTION:\nDesign a reusable skill that satisfies the goal. Use only the tools in context. If you need more info, ask concise questions.\n\nGOAL:\n${goal}\n\nCONTEXT:\nAvailable Tools:\n${tools}\n\nCURRENT CONSTRAINTS:\n${constraints}\n\nOPEN QUESTIONS:\n${questions}\n\nOUTPUT:\nReturn a JSON object with keys:\n- skill_id (kebab-case, e.g. "docs-to-files")\n- summary (1-2 sentences)\n- interface (array of function signatures)\n- bindings (object of alias -> server_prefix)\n- fanout_tools (array of tool qualified names)\n- code (Python for lib.py)\n- questions (array of follow-up questions if needed)\n`;

    return { system: SYSTEM_PROMPT, user: userPrompt };
}

export const SYSTEM_PROMPT_REPAIR = `You are a JSON repair bot. Fix invalid JSON only.`;

export function buildRepairPrompt(raw: string): { system: string; user: string } {
    const userPrompt = `The following JSON is invalid. Fix it and return only valid JSON.\n\nINVALID:\n${raw}`;
    return { system: SYSTEM_PROMPT_REPAIR, user: userPrompt };
}
