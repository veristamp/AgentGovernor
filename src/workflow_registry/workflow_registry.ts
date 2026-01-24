import { existsSync, mkdirSync, readFileSync, readdirSync, writeFileSync } from 'fs';
import { join, resolve } from 'path';
import { RegistryDatabase } from '../registry/db';
import type { StoredWorkflow, WorkflowManifest, WorkflowMetadata, WorkflowRegistryOptions, WorkflowSearchResult } from './types';

function slugify(value: string): string {
    return value
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, '-')
        .replace(/^-+|-+$/g, '')
        .slice(0, 40) || 'workflow';
}

export class WorkflowRegistry {
    private db;
    private baseDir: string;

    constructor(options: WorkflowRegistryOptions = {}) {
        this.baseDir = resolve(options.baseDir ?? 'workflows_gcm');
        this.db = RegistryDatabase.getInstance(options.dbPath).getDb();
    }

    public ingest(orgId?: string) {
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
                    this.upsert(metadata, code);
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

    private upsert(meta: WorkflowMetadata, code: string) {
        const insert = this.db.prepare(`
            INSERT OR REPLACE INTO workflows (workflow_id, org_id, goal, summary, code, metadata_json)
            VALUES ($id, $org, $goal, $summary, $code, $json)
        `);

        insert.run({
            $id: meta.id,
            $org: meta.orgId || 'personal',
            $goal: meta.goal,
            $summary: meta.summary || '',
            $code: code,
            $json: JSON.stringify(meta)
        });
    }

    public saveWorkflow(
        goal: string,
        code: string,
        manifest: WorkflowManifest,
        identity: { id: string; orgId?: string },
        summary?: string
    ): StoredWorkflow {
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
        this.upsert(metadata, code);

        return stored;
    }

    public search(
        goal: string,
        allowedSkills: string[],
        orgId?: string,
        limit: number = 3
    ): WorkflowSearchResult[] {
        const org = orgId ?? 'personal';
        const sanitized = goal.replace(/[^\w\s]/g, '').trim();
        
        // If empty query, list recent
        if (!sanitized) {
            return this.listWorkflows(org).slice(0, limit).map(w => ({ metadata: w.metadata, score: 1 }));
        }

        const ftsQuery = this.db.prepare(`
            SELECT workflow_id, rank 
            FROM workflows_fts 
            WHERE workflows_fts MATCH $query 
            ORDER BY rank 
            LIMIT $limit * 2
        `);

        const matches = ftsQuery.all({
            $query: sanitized + "*",
            $limit: limit
        }) as { workflow_id: string, rank: number }[];

        if (matches.length === 0) return [];

        // Fetch full rows and filter by Org + Skills
        const placeholders = matches.map(() => '?').join(',');
        const rows = this.db.prepare(`SELECT * FROM workflows WHERE workflow_id IN (${placeholders})`)
            .all(...matches.map(m => m.workflow_id)) as any[];

        const results: WorkflowSearchResult[] = [];
        const allowedSet = new Set(allowedSkills);

        for (const row of rows) {
            if (row.org_id !== org) continue; // Enforce Org Isolation

            const meta = JSON.parse(row.metadata_json) as WorkflowMetadata;
            
            // Skill Permission Check
            const requiredSkills = meta.skills || [];
            if (requiredSkills.some(s => !allowedSet.has(s))) {
                continue; // Skip if user lacks permission for a skill used in this workflow
            }

            // Find rank from matches
            const match = matches.find(m => m.workflow_id === row.workflow_id);
            results.push({
                metadata: meta,
                score: match ? -match.rank : 0 // FTS rank is negative (lower is better)
            });
        }

        return results.slice(0, limit);
    }

    public listWorkflows(orgId?: string): StoredWorkflow[] {
        const org = orgId ?? 'personal';
        const query = this.db.prepare('SELECT * FROM workflows WHERE org_id = ? ORDER BY workflow_id DESC');
        const rows = query.all(org) as any[];

        return rows.map(row => ({
            metadata: JSON.parse(row.metadata_json),
            manifest: { 
                skills: JSON.parse(row.metadata_json).skills,
                tools: [] // Default to empty tools as they are usually inferred or not stored in simple metadata
            }, 
            code: row.code
        }));
    }
}
