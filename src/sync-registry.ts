#!/usr/bin/env bun
import { ToolRegistry } from './tool_registry/registry';
import { SkillRegistry } from './skills_registry/registry';
import { WorkflowRegistry } from './workflow_registry/workflow_registry';

async function main() {
    console.log('🔄 Starting full registry sync...');

    try {
        // 1. Sync Tools
        console.log('\n🛠️  Syncing Tools...');
        const toolRegistry = new ToolRegistry();
        await toolRegistry.ingest();

        // 2. Sync Skills
        console.log('\n🧠 Syncing Skills...');
        const skillRegistry = new SkillRegistry();
        await skillRegistry.ingest();

        // 3. Sync Workflows
        console.log('\n📋 Syncing Workflows...');
        const workflowRegistry = new WorkflowRegistry();
        await workflowRegistry.ingest();

        console.log('\n✅ Registry sync complete!');
        process.exit(0);
    } catch (error) {
        console.error('\n❌ Registry sync failed:', error);
        process.exit(1);
    }
}

main();
