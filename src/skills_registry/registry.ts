import { readFileSync, existsSync, readdirSync, writeFileSync, mkdirSync } from 'fs';
import { join, resolve } from 'path';
import { RegistryDatabase } from '../registry/db';

export interface SkillSummary {
    skillRef: string;
    skillId: string;
    version: string;
    description: string;
    interfaces: string[];
    bindings: Record<string, string>;
    fanoutTools: string[];
}

export interface SkillSearchResult {
    skillRef: string;
    description: string;
    interfaces: string[];
    bindings: Record<string, string>;
    fanoutTools: string[];
}

const DEFAULT_SKILLS_DIR = resolve('skills');

export class SkillRegistry {
    private db;
    private skillsDir: string;

    constructor(skillsDir: string = DEFAULT_SKILLS_DIR, dbPath?: string) {
        this.skillsDir = resolve(skillsDir);
        this.db = RegistryDatabase.getInstance(dbPath).getDb();
    }

    /**
     * Load skills (alias for ingest for compatibility)
     */
    public load() {
        this.ingest();
    }

    /**
     * Scan disk and populate SQLite
     */
    public ingest() {
        if (!existsSync(this.skillsDir)) return;
        
        const entries = readdirSync(this.skillsDir, { withFileTypes: true });
        let count = 0;

        for (const entry of entries) {
            if (!entry.isDirectory()) continue;
            const skillDir = join(this.skillsDir, entry.name);
            
            try {
                const summary = this.readSkillFromDisk(skillDir);
                if (summary) {
                    this.upsert(summary);
                    count++;
                }
            } catch (e) {
                console.error(`[SkillRegistry] Failed to load skill ${entry.name}:`, e);
            }
        }
        
        if (count > 0) {
            console.log(`[SkillRegistry] Ingested ${count} skills.`);
        }
    }

    private readSkillFromDisk(skillDir: string): SkillSummary | null {
        const manifestPath = join(skillDir, 'manifest.json');
        if (!existsSync(manifestPath)) return null;

        const raw = readFileSync(manifestPath, 'utf-8');
        const data = JSON.parse(raw);
        const skillId = String(data.skillId ?? '').trim();
        if (!skillId) return null;

        const version = String(data.version ?? 1);
        const skillRef = `skills:${skillId}@${version}`;

        // Read docs
        const docPath = join(skillDir, 'SKILL.md');
        let description = '';
        let interfaces: string[] = [];
        
        if (existsSync(docPath)) {
            const docContent = readFileSync(docPath, 'utf-8');
            // Simple parsing logic (can be refined)
            const firstLine = docContent.split('\n')[0];
            description = (firstLine ?? '').replace(/^#\s+/, '').trim(); // Fallback to title? 
            // Better: Find first non-header line
            const lines = docContent.split('\n');
            for (const line of lines) {
                if (line.trim() && !line.startsWith('#')) {
                    description = line.trim();
                    break;
                }
            }
            
            // Extract interface blocks
            // This is a simplified parser, keeping it robust
            if (data.interfaces && Array.isArray(data.interfaces)) {
                interfaces = data.interfaces;
            } else {
                // Fallback to legacy parsing if needed (omitted for brevity, assume manifest has it or basic scan)
                interfaces = []; 
            }
        }

        return {
            skillRef,
            skillId,
            version,
            description: data.description || description,
            interfaces: data.interfaces || interfaces,
            bindings: data.bindings || {},
            fanoutTools: data.fanoutTools || []
        };
    }

    private upsert(skill: SkillSummary) {
        const insert = this.db.prepare(`
            INSERT OR REPLACE INTO skills (skill_ref, skill_id, version, description, manifest_json, interfaces_json)
            VALUES ($ref, $id, $ver, $desc, $manifest, $interfaces)
        `);

        insert.run({
            $ref: skill.skillRef,
            $id: skill.skillId,
            $ver: skill.version,
            $desc: skill.description,
            $manifest: JSON.stringify({
                bindings: skill.bindings,
                fanoutTools: skill.fanoutTools
            }),
            $interfaces: JSON.stringify(skill.interfaces)
        });
    }

    public search(query: string, limit: number = 20): SkillSummary[] {
        const sanitized = query.replace(/[^\w\s]/g, '').trim();
        if (!sanitized) return this.listAll().slice(0, limit); // Fallback to list

        const ftsQuery = this.db.prepare(`
            SELECT skill_ref 
            FROM skills_fts 
            WHERE skills_fts MATCH $query 
            ORDER BY rank 
            LIMIT $limit
        `);

        const results = ftsQuery.all({ 
            $query: sanitized + "*", 
            $limit: limit 
        }) as { skill_ref: string }[];

        if (results.length === 0) return [];

        const placeholders = results.map(() => '?').join(',');
        const finalQuery = this.db.prepare(`
            SELECT * FROM skills WHERE skill_ref IN (${placeholders})
        `);

        const rows = finalQuery.all(...results.map(r => r.skill_ref)) as any[];
        return rows.map(this.mapRow);
    }

    public listAll(): SkillSummary[] {
        const query = this.db.query('SELECT * FROM skills');
        const rows = query.all() as any[];
        return rows.map(this.mapRow);
    }

    public inspect(skillRef: string): SkillSummary | null {
        const query = this.db.prepare('SELECT * FROM skills WHERE skill_ref = ?');
        const row = query.get(skillRef) as any;
        if (!row) return null;
        return this.mapRow(row);
    }

    private mapRow(row: any): SkillSummary {
        const manifest = JSON.parse(row.manifest_json);
        return {
            skillRef: row.skill_ref,
            skillId: row.skill_id,
            version: row.version,
            description: row.description,
            interfaces: JSON.parse(row.interfaces_json),
            bindings: manifest.bindings,
            fanoutTools: manifest.fanoutTools
        };
    }
}
