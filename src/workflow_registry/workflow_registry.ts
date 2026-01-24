import { existsSync, mkdirSync, readFileSync, readdirSync, writeFileSync } from 'fs';
import { join, resolve } from 'path';
import type { StoredWorkflow, WorkflowManifest, WorkflowMetadata, WorkflowRegistryOptions, WorkflowSearchResult } from './types';

function slugify(value: string): string {
    return value
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, '-')
        .replace(/^-+|-+$/g, '')
        .slice(0, 40) || 'workflow';
}

function scoreText(query: string, text: string): number {
    const tokens = query.toLowerCase().split(/\W+/).filter(Boolean);
    const hay = text.toLowerCase();
    let score = 0;
    for (const token of tokens) {
        if (hay.includes(token)) score += 1;
    }
    return score;
}

export class WorkflowRegistry {
    private baseDir: string;

    constructor(options: WorkflowRegistryOptions = {}) {
        this.baseDir = resolve(options.baseDir ?? 'workflows_gcm');
    }

    saveWorkflow(
        goal: string,
        code: string,
        manifest: WorkflowManifest,
        identity: { id: string; orgId?: string },
        summary?: string
    ): StoredWorkflow {
        const org = identity.orgId ?? 'personal';
        const workflowId = `${slugify(goal)}-${Date.now()}`;
        const workflowDir = join(this.baseDir, org, workflowId);
        mkdirSync(workflowDir, { recursive: true });

        const metadata: WorkflowMetadata = {
            id: workflowId,
            goal,
            createdAt: new Date().toISOString(),
            createdBy: identity.id,
            orgId: identity.orgId,
            skills: manifest.skills ?? [],
            summary,
        };

        const stored: StoredWorkflow = {
            metadata,
            manifest,
            code,
        };

        writeFileSync(join(workflowDir, 'metadata.json'), JSON.stringify(metadata, null, 2));
        writeFileSync(join(workflowDir, 'manifest.json'), JSON.stringify(manifest, null, 2));
        writeFileSync(join(workflowDir, 'workflow.py'), code.trim() + '\n');

        return stored;
    }

    listWorkflows(orgId?: string): StoredWorkflow[] {
        const org = orgId ?? 'personal';
        const orgDir = join(this.baseDir, org);
        if (!existsSync(orgDir)) return [];
        const entries = readdirSync(orgDir, { withFileTypes: true });
        const results: StoredWorkflow[] = [];

        for (const entry of entries) {
            if (!entry.isDirectory()) continue;
            const workflowDir = join(orgDir, entry.name);
            const metadataPath = join(workflowDir, 'metadata.json');
            const manifestPath = join(workflowDir, 'manifest.json');
            const workflowPath = join(workflowDir, 'workflow.py');
            if (!existsSync(metadataPath) || !existsSync(manifestPath) || !existsSync(workflowPath)) {
                continue;
            }
            const metadata = JSON.parse(readFileSync(metadataPath, 'utf-8')) as WorkflowMetadata;
            const manifest = JSON.parse(readFileSync(manifestPath, 'utf-8')) as WorkflowManifest;
            const code = readFileSync(workflowPath, 'utf-8');
            results.push({ metadata, manifest, code });
        }

        return results;
    }

    search(
        goal: string,
        allowedSkills: string[],
        orgId?: string,
        limit: number = 3
    ): WorkflowSearchResult[] {
        const workflows = this.listWorkflows(orgId);
        const allowed = new Set(allowedSkills);
        const scored: WorkflowSearchResult[] = [];

        for (const workflow of workflows) {
            if (workflow.manifest.skills.some((skill) => !allowed.has(skill))) {
                continue;
            }
            const text = [workflow.metadata.goal, workflow.metadata.summary, ...workflow.metadata.skills].join(' ');
            const score = scoreText(goal, text);
            if (score <= 0) continue;
            scored.push({ metadata: workflow.metadata, score });
        }

        return scored
            .sort((a, b) => b.score - a.score || a.metadata.id.localeCompare(b.metadata.id))
            .slice(0, limit);
    }
}
