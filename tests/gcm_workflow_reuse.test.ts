import { test, expect } from 'bun:test';
import { Agent } from '../src/agent';
import { LlmClient } from '../src/agent';
import { PolicyEngine } from '../src/policy';
import { WorkflowRegistry } from '../src/workflow_registry';
import { rmSync, existsSync } from 'fs';
import { resolve } from 'path';

class FakeWorkflowLlm extends LlmClient {
    private callCount = 0;

    constructor() {
        super('http://localhost', '');
    }

    override async complete(messages: { role: string; content: string }[]): Promise<string> {
        this.callCount += 1;
        const prompt = messages.map((message) => message.content).join('\n');
        if (this.callCount > 1 && !prompt.includes('Workflow Examples:')) {
            throw new Error('Workflow examples were not provided on reuse.');
        }

        return [
            '```python',
            '# PLAN: Use docs-to-files + repo-insight',
            'import skills',
            '',
            'async def main():',
            '    docs = await skills.load("docs-to-files").fetch_and_store(library="/vercel/next.js", topic="routing", output_dir="output/docs")',
            '    report = await skills.load("repo-insight").analyze_repo(query="Next.js routing docs summary", output_dir="output/reports", note_key="routing_docs_summary", write_report=True)',
            '    return {"docs": docs, "report": report}',
            '```',
        ].join('\n');
    }
}

test('agent saves and reuses multi-skill workflows', async () => {
    const baseDir = resolve('workflows_gcm');
    if (existsSync(baseDir)) {
        rmSync(baseDir, { recursive: true, force: true });
    }

    const registry = new WorkflowRegistry({ baseDir });
    const agent = new Agent({
        llm: new FakeWorkflowLlm(),
        policy: new PolicyEngine(),
        model: 'test-model',
        workflowRegistry: registry,
        maxRepairAttempts: 1,
    });

    const identity: { roles: string[]; scopes: string[]; orgId: string } = {
        roles: ['mcp:docs-curator', 'mcp:repo-inspector'],
        scopes: [],
        orgId: 'org-1',
    };
    await agent.run({
        goal: 'Fetch docs then write repo insight summary',
        identity,
    });

    const stored = await registry.listWorkflows('org-1');
    expect(stored.length).toBeGreaterThan(0);
    expect(stored[0]?.manifest.skills).toContain('skills:docs-to-files@1');
    expect(stored[0]?.manifest.skills).toContain('skills:repo-insight@1');

    await agent.run({
        goal: 'Fetch docs then write repo insight summary',
        identity,
    });
});
