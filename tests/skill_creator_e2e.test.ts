import { test, expect } from 'bun:test';
import { LlmClient } from '../src/agent';
import { SkillCreatorAgent } from '../src/skill_creator';
import { PolicyEngine } from '../src/policy';
import { existsSync, readFileSync, rmSync } from 'fs';
import { resolve } from 'path';

class FakeSkillLlm extends LlmClient {
    private callCount = 0;

    constructor() {
        super('http://localhost', '');
    }

    override async complete(messages: { role: string; content: string }[]): Promise<string> {
        this.callCount += 1;
        const prompt = messages.map((message) => message.content).join('\n');

        if (!prompt.includes('CONTEXT:') || !prompt.includes('Available Tools:')) {
            throw new Error('Skill prompt missing RICECO context.');
        }

        if (this.callCount === 1) {
            return JSON.stringify({
                skill_id: 'docs-skill',
                summary: 'Fetch docs and store them locally.',
                interface: ['fetch_docs(library, topic, output_dir, file_name=None)'],
                bindings: { ctx: 'context7', fs: 'filesystem' },
                fanout_tools: ['context7.query-docs', 'filesystem.write-file'],
                code: 'async def fetch_docs(library, topic, output_dir, file_name=None):\n    return {}',
                questions: [],
            });
        }

        if (!prompt.includes('Missing required tools')) {
            throw new Error('Tool expansion loop did not add missing tools.');
        }

        return JSON.stringify({
            skill_id: 'docs-skill',
            summary: 'Fetch docs and store them locally.',
            interface: ['fetch_docs(library, topic, output_dir, file_name=None)'],
            bindings: { ctx: 'context7', fs: 'filesystem' },
            fanout_tools: [
                'context7.resolve-library-id',
                'context7.query-docs',
                'filesystem.create-directory',
                'filesystem.write-file',
            ],
            code: 'async def fetch_docs(library, topic, output_dir, file_name=None):\n    return {}',
            questions: [],
        });
    }
}

test('skill creator agent end-to-end', async () => {
    const skillDir = resolve('skills', 'docs-skill');
    if (existsSync(skillDir)) {
        rmSync(skillDir, { recursive: true, force: true });
    }

    const policyPath = resolve('policy', 'policy_rules.json');
    const policyBefore = readFileSync(policyPath, 'utf-8');

    const agent = new SkillCreatorAgent(
        { llm: new FakeSkillLlm(), policy: new PolicyEngine() },
        {
            model: 'test-model',
            toolsPath: 'tools_schema.json',
            skillsDir: 'skills',
            policyFilePath: policyPath,
            rolePermissionsPath: 'policy/role_permissions.json',
            maxRepairAttempts: 2,
        }
    );

    const result = await agent.run({
        goal: 'Fetch documentation and store it in a file',
        requester: {
            id: 'admin',
            roles: ['mcp:admin', 'mcp:docs-curator'],
            orgId: 'org-1',
        },
    });

    expect(result.skillRef).toBe('skills:docs-skill@1');
    expect(result.rolesGranted).toContain('mcp:docs-curator');
    expect(result.abacProposal?.action).toBe('skills:docs-skill@1');
    expect(result.abacProposal?.conditions.allowedOrgIds).toContain('org-1');

    const manifestPath = resolve(skillDir, 'manifest.json');
    const skillMdPath = resolve(skillDir, 'SKILL.md');
    const libPath = resolve(skillDir, 'lib.py');

    expect(existsSync(manifestPath)).toBe(true);
    expect(existsSync(skillMdPath)).toBe(true);
    expect(existsSync(libPath)).toBe(true);

    const manifest = JSON.parse(readFileSync(manifestPath, 'utf-8')) as { fanoutTools?: string[] };
    expect(manifest.fanoutTools).toContain('filesystem.write-file');

    const skillMd = readFileSync(skillMdPath, 'utf-8');
    expect(skillMd).toContain('## Interface');

    const policyAfter = readFileSync(policyPath, 'utf-8');
    expect(policyAfter).toBe(policyBefore);
});
