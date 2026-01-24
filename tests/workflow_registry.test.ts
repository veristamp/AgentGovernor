import { test, expect } from 'bun:test';
import { WorkflowRegistry } from '../src/workflow_registry';
import { rmSync, existsSync } from 'fs';
import { resolve } from 'path';

const baseDir = resolve('workflows_gcm');

test('workflow registry saves and filters by org + skills', () => {
    if (existsSync(baseDir)) {
        rmSync(baseDir, { recursive: true, force: true });
    }

    const registry = new WorkflowRegistry({ baseDir });
    const manifest = { skills: ['skills:docs-to-files@1'], tools: ['docs-to-files.fetch_and_store'] };

    const stored = registry.saveWorkflow('Fetch docs', 'async def main():\n    return {}', manifest, {
        id: 'user1',
        orgId: 'org-1',
    });

    expect(stored.metadata.orgId).toBe('org-1');

    const matches = registry.search('fetch docs', ['skills:docs-to-files@1'], 'org-1');
    expect(matches.length).toBe(1);
    expect(matches[0]?.metadata.id).toBe(stored.metadata.id);

    const denied = registry.search('fetch docs', ['skills:repo-insight@1'], 'org-1');
    expect(denied.length).toBe(0);
});
