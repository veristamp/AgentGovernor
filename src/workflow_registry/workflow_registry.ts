import { existsSync, mkdirSync, readFileSync, readdirSync, writeFileSync } from 'fs';
import { join, resolve } from 'path';
import { db, toTsVector } from '../registry/db';
import { workflows } from '../registry/schema';
import { sql, eq } from 'drizzle-orm';
import type { StoredWorkflow, WorkflowManifest, WorkflowMetadata, WorkflowRegistryOptions, WorkflowSearchResult } from './types';

function slugify(value: string): string {
    return value
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, '-')
        .replace(/^-+|-+$/g, '')
        .slice(0, 40) || 'workflow';
}

export class WorkflowRegistry {
    private baseDir: string;

    constructor(options: WorkflowRegistryOptions = {}) {
        this.baseDir = resolve(options.baseDir ?? 'workflows_gcm');
    }

    public async ingest(orgId?: string) {
        const org = orgId ?? 'personal';
        const orgDir = join(this.baseDir, org);
        if (!existsSync(orgDir)) return;

        const entries = readdirSync(orgDir, { withFileTypes: true });
        let count = 0;

        for (const entry of entries) {
            if (!entry.isDirectory()) continue;
            const workflowDir = join(orgDir, entry.name);
            const metadataPath = join(workflowDir, 'metadata.json');
            const codePath = join(workflowDir, 'workflow.py');

            if (existsSync(metadataPath) && existsSync(codePath)) {
                try {
                    const metadata = JSON.parse(readFileSync(metadataPath, 'utf-8'));
                    const code = readFileSync(codePath, 'utf-8');
                    await this.upsert(metadata, code);
                    count++;
                } catch (e) {
                    console.error(`[WorkflowRegistry] Failed to load ${entry.name}:`, e);
                }
            }
        }
        if (count > 0) {
            console.log(`[WorkflowRegistry] Ingested ${count} workflows for ${org}.`);
        }
    }

    private async upsert(meta: WorkflowMetadata, code: string) {
        const searchText = `${meta.goal} ${meta.summary || ''} ${(meta.skills || []).join(' ')}`;
        
        await db.insert(workflows).values({
            workflowId: meta.id,
            orgId: meta.orgId || 'personal',
            goal: meta.goal,
            summary: meta.summary || '',
            code: code,
            metadata: meta as unknown as Record<string, unknown>,
            searchVector: toTsVector(searchText)
        }).onConflictDoUpdate({
            target: workflows.workflowId,
            set: {
                goal: meta.goal,
                summary: meta.summary || '',
                code: code,
                metadata: meta as unknown as Record<string, unknown>,
                searchVector: toTsVector(searchText)
            }
        });
    }

    public async saveWorkflow(
        goal: string,
        code: string,
        manifest: WorkflowManifest,
        identity: { id: string; orgId?: string },
        summary?: string
    ): Promise<StoredWorkflow> {
        const org = identity.orgId ?? 'personal';
        const workflowId = `${slugify(goal)}-${Date.now()}`;
        const workflowDir = join(this.baseDir, org, workflowId);
        
        // 1. Save to Disk (Source of Truth)
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

        // 2. Sync to DB
        await this.upsert(metadata, code);

        return stored;
    }

    public async search(
        goal: string,
        allowedSkills: string[],
        orgId?: string,
        limit: number = 3
    ): Promise<WorkflowSearchResult[]> {
        const org = orgId ?? 'personal';
        const sanitized = goal.replace(/[^\w\s]/g, '').trim();
        
        // If empty query, list recent
        if (!sanitized) {
            const list = await this.listWorkflows(org);
            return list.slice(0, limit).map(w => ({ metadata: w.metadata, score: 1 }));
        }

        const tokens = sanitized.split(/\s+/).filter(t => t.length > 2);
        if (tokens.length === 0) {
             const list = await this.listWorkflows(org);
             return list.slice(0, limit).map(w => ({ metadata: w.metadata, score: 1 }));
        }
        
        const searchQuery = tokens.join(' | ');

        const matches = await db.select()
            .from(workflows)
            .where(
                sql`org_id = ${org} AND search_vector @@ to_tsquery('english', ${searchQuery})`
            )
            .limit(limit * 2);

        const results: WorkflowSearchResult[] = [];
        const allowedSet = new Set(allowedSkills);

        for (const row of matches) {
            const meta = row.metadata as unknown as WorkflowMetadata;
            
            // Skill Permission Check
            const requiredSkills = meta.skills || [];
            if (requiredSkills.some(s => !allowedSet.has(s))) {
                continue; // Skip if user lacks permission for a skill used in this workflow
            }

            results.push({
                metadata: meta,
                score: 1 // Rank handled by DB ordering implicitly or we can use ts_rank
            });
        }

        return results.slice(0, limit);
    }

    public async listWorkflows(orgId?: string): Promise<StoredWorkflow[]> {
        const org = orgId ?? 'personal';
        // const query = this.db.prepare('SELECT * FROM workflows WHERE org_id = ? ORDER BY workflow_id DESC');
        // const rows = query.all(org) as any[];
        
        const rows = await db.select()
            .from(workflows)
            .where(eq(workflows.orgId, org));

        return rows.map(row => ({
            metadata: row.metadata as unknown as WorkflowMetadata,
            manifest: { 
                skills: (row.metadata as unknown as WorkflowMetadata).skills,
                tools: [] 
            }, 
            code: row.code
        }));
    }
}
