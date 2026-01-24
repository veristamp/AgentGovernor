import { test, expect } from 'bun:test';
import { Agent, LlmClient } from '../src/agent';
import { PolicyEngine } from '../src/policy/engine';
import { analyzeCode } from '../src/audit';

const LLM_BASE = process.env.TEST_LLM_BASE ?? 'http://localhost:1234/v1';
const LLM_MODEL = process.env.TEST_LLM_MODEL ?? 'liquid/lfm2.5-1.2b';

const goal = 'Fetch Next.js routing docs and store them in output/docs';

test('agent end-to-end with local LLM', async () => {
    const agent = new Agent({
        llm: new LlmClient(LLM_BASE, ''),
        policy: new PolicyEngine(),
        model: LLM_MODEL,
        temperature: 0.3,
        maxTokens: 1200,
        maxRepairAttempts: 2,
    });

    const result = await agent.run({
        goal,
        identity: {
            roles: ['mcp:docs-curator'],
            scopes: [],
        },
    });

    expect(result.selectedSkills).not.toContain('skills:repo-insight@1');
    expect(result.prompt).toContain('CONTEXT:');
    expect(result.prompt).toContain('EXAMPLES:');
    expect(result.code).toContain('async def main');

    const manifest = await analyzeCode(result.code);
    if (manifest.errors.length) {
        throw new Error(`Audit errors: ${manifest.errors.join(', ')}`);
    }
    const matchedSkill = manifest.skills.some((skill) => result.selectedSkills.includes(skill));
    expect(matchedSkill).toBe(true);
    expect(manifest.toolCalls.length).toBeGreaterThan(0);

});
