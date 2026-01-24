import type { AgentPromptContext } from './types';

const SYSTEM_PROMPT = `You are The Code Orchestrator.
You must write Python code that ONLY calls skills provided in the SKILLS CONTEXT.

Rules:
1. Output ONLY a single Python code block.
2. Define exactly one async def main() function.
3. Only use skills via: import skills; <var> = skills.load("<skill-id>").
4. Call skill functions exactly as shown in the SKILLS CONTEXT.
5. Use await for all skill calls.
6. Start with a # PLAN: comment.
7. Return a meaningful result from main().
8. If the output fails validation, you will be asked to repair the code.`;

function parseSkillId(skillRef: string): string | null {
    const match = skillRef.match(/^skills:([^@]+)@/i);
    return match?.[1] ?? null;
}

function formatRicecoContext(context: AgentPromptContext): string {
    const lines: string[] = [];
    lines.push('CONTEXT:');
    lines.push('Available Skills:');

    if (!context.skills.length) {
        lines.push('- (no skills available)');
    }

    for (const skill of context.skills) {
        lines.push(`- skill_ref: ${skill.skillRef}`);
        if (skill.description) {
            lines.push(`  description: ${skill.description}`);
        }
        if (Object.keys(skill.bindings).length) {
            lines.push('  bindings:');
            for (const [alias, server] of Object.entries(skill.bindings)) {
                lines.push(`    - ${alias}: ${server}`);
            }
        }
        if (skill.interfaces.length) {
            lines.push('  interfaces:');
            for (const signature of skill.interfaces) {
                lines.push(`    - ${signature}`);
            }
        }
        if (skill.fanoutTools.length) {
            lines.push('  fanout_tools:');
            for (const tool of skill.fanoutTools) {
                lines.push(`    - ${tool}`);
            }
        }

        if (context.selectedSkill?.skillRef === skill.skillRef) {
            lines.push('  selected: true');
        }
        lines.push('');
    }

    if (context.workflowExamples?.length) {
        lines.push('Workflow Examples:');
        for (const workflow of context.workflowExamples) {
            lines.push(`- id: ${workflow.id}`);
            lines.push(`  goal: ${workflow.goal}`);
            if (workflow.summary) {
                lines.push(`  summary: ${workflow.summary}`);
            }
            if (workflow.skills.length) {
                lines.push('  skills:');
                for (const skill of workflow.skills) {
                    lines.push(`    - ${skill}`);
                }
            }
            lines.push('');
        }
    }

    return lines.join('\n');
}

function buildExamplesSection(context: AgentPromptContext): string {
    const lines: string[] = [];
    lines.push('EXAMPLES:');

    const selected = context.selectedSkill;
    if (!selected || !selected.interfaces.length) {
        lines.push('(No examples available. Use the context above.)');
        return lines.join('\n');
    }

    const skillId = parseSkillId(selected.skillRef) ?? 'skill_name';
    const method = selected.interfaces[0]?.split('(')[0]?.trim() ?? 'method';

    lines.push('```python');
    lines.push(`# PLAN: Use ${skillId} to complete the task`);
    lines.push('');
    lines.push('import skills');
    lines.push('');
    lines.push('async def main():');
    lines.push(`    result = await skills.load("${skillId}").${method}(...)`);
    lines.push('    return result');
    lines.push('```');

    return lines.join('\n');
}

export const SYSTEM_PROMPT_REPAIR = `You are a Python code auto-correcting bot. Fix broken Python code and return a single corrected Python code block only.`;

export function buildPrompt(goal: string, context: AgentPromptContext): { system: string; user: string } {
    const instruction = `INSTRUCTION:\nGenerate Python code to accomplish the goal using only the skills listed in the context.\nIf the code fails validation, you may be asked to repair it.\nReturn only a single fenced Python code block.`;
    const output = `OUTPUT:\n\n\n\`\`\`python\n# PLAN: ...\n\nasync def main():\n    ...\n\`\`\`\n`;

    const userPrompt = `ROLE:\nYou are The Code Orchestrator.\n\n${instruction}\n\nGOAL:\n${goal}\n\n${formatRicecoContext(context)}\n\n${buildExamplesSection(context)}\n\nCONSTRAINTS:\n1. Use only skills listed in the context.\n2. Load skills with: import skills; <var> = skills.load("<skill-id>").\n3. All skill calls must be awaited.\n4. Define exactly one async def main().\n5. Begin with a # PLAN: comment describing the steps.\n6. Return a meaningful result.\n\n${output}`;

    return { system: SYSTEM_PROMPT, user: userPrompt };
}

export function buildRepairPrompt(
    goal: string,
    context: AgentPromptContext,
    code: string,
    errors: string[]
): { system: string; user: string } {
    const errorLines = errors.length ? errors.map((err) => `- ${err}`).join('\n') : '- Unknown error';
    const output = `OUTPUT:\n\n\n\`\`\`python\n# PLAN: ...\n\nasync def main():\n    ...\n\`\`\`\n`;

    const constraints = `CONSTRAINTS:\n1. Use only skills listed in the context.\n2. Load skills with: import skills; <var> = skills.load("<skill-id>").\n3. All skill calls must be awaited.\n4. Define exactly one async def main().\n5. Begin with a # PLAN: comment describing the steps.\n6. Return a meaningful result.`;

    const userPrompt = `ROLE:\nYou are The Code Orchestrator repairing a failed attempt.\n\nINSTRUCTION:\nFix the broken code so it satisfies the constraints. Return only a single fenced Python code block.\n\nGOAL:\n${goal}\n\n${formatRicecoContext(context)}\n\n${buildExamplesSection(context)}\n\nERRORS:\n${errorLines}\n\nBROKEN CODE:\n\`\`\`python\n${code}\n\`\`\`\n\n${constraints}\n\n${output}`;

    return { system: SYSTEM_PROMPT_REPAIR, user: userPrompt };
}
