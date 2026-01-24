import { readdir } from 'node:fs/promises';
import { join, resolve } from 'path';
import { db, toTsVector } from '../registry/db';
import { skills } from '../registry/schema';
import { sql, eq } from 'drizzle-orm';

export interface SkillSummary {
    skillRef: string;
    skillId: string;
    version: string;
    description: string;
    interfaces: string[];
    bindings: Record<string, string>;
    fanoutTools: string[];
}

// Re-export for compatibility
export interface SkillSearchResult extends SkillSummary {}

const DEFAULT_SKILLS_DIR = resolve('skills');

export class SkillRegistry {
    private skillsDir: string;

    constructor(skillsDir: string = DEFAULT_SKILLS_DIR, dbPath?: string) {
        this.skillsDir = resolve(skillsDir);
    }

    /**
     * Scan disk and populate Postgres
     */
    public async ingest() {
        try {
            const entries = await readdir(this.skillsDir, { withFileTypes: true });
            let count = 0;

            for (const entry of entries) {
                if (!entry.isDirectory()) continue;
                const skillDir = join(this.skillsDir, entry.name);
                
                try {
                    const summary = await this.readSkillFromDisk(skillDir);
                    if (summary) {
                        await this.upsert(summary);
                        count++;
                    }
                } catch (e) {
                    console.error(`[SkillRegistry] Failed to load skill ${entry.name}:`, e);
                }
            }
            
            if (count > 0) {
                console.log(`[SkillRegistry] Ingested ${count} skills.`);
            }
        } catch (e) {
            // Directory might not exist
        }
    }

    private async readSkillFromDisk(skillDir: string): Promise<SkillSummary | null> {
        const manifestPath = join(skillDir, 'manifest.json');
        if (!(await Bun.file(manifestPath).exists())) return null;

        const raw = await Bun.file(manifestPath).text();
        const data = JSON.parse(raw);
        const skillId = String(data.skillId ?? '').trim();
        if (!skillId) return null;

        const version = String(data.version ?? 1);
        const skillRef = `skills:${skillId}@${version}`;

        // Read docs
        const docPath = join(skillDir, 'SKILL.md');
        let description = '';
        let interfaces: string[] = [];
        
        if (await Bun.file(docPath).exists()) {
            const docContent = await Bun.file(docPath).text();
            const firstLine = docContent.split('\n')[0];
            description = (firstLine ?? '').replace(/^#\s+/, '').trim(); 
            const lines = docContent.split('\n');
            for (const line of lines) {
                if (line.trim() && !line.startsWith('#')) {
                    description = line.trim();
                    break;
                }
            }
            if (data.interfaces && Array.isArray(data.interfaces)) {
                interfaces = data.interfaces;
            } else {
                // Parse interfaces from SKILL.md
                let inInterfaceSection = false;
                for (const line of lines) {
                    if (line.match(/^##\s+Interface/i)) {
                        inInterfaceSection = true;
                        continue;
                    }
                    if (inInterfaceSection) {
                        if (line.startsWith('##')) break; 
                        const match = line.match(/[`']?([\w_]+\([^)]*\))[`']?/);
                        if (match) {
                            interfaces.push(match[1] as string);
                        }
                    }
                }
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

    private async upsert(skill: SkillSummary) {
        const interfacesJson = skill.interfaces;
        const searchText = `${skill.skillRef} ${skill.skillId} ${skill.description} ${skill.interfaces.join(' ')}`;

        await db.insert(skills).values({
            skillRef: skill.skillRef,
            skillId: skill.skillId,
            version: skill.version,
            description: skill.description,
            manifest: {
                bindings: skill.bindings,
                fanoutTools: skill.fanoutTools
            },
            interfaces: interfacesJson,
            searchVector: toTsVector(searchText)
        }).onConflictDoUpdate({
            target: skills.skillRef,
            set: {
                description: skill.description,
                manifest: {
                    bindings: skill.bindings,
                    fanoutTools: skill.fanoutTools
                },
                interfaces: interfacesJson,
                searchVector: toTsVector(searchText)
            }
        });
    }

    public async search(query: string, limit: number = 20): Promise<SkillSummary[]> {
        const sanitized = query.replace(/[^\w\s]/g, '').trim();
        if (!sanitized) return (await this.listAll()).slice(0, limit);

        const tokens = sanitized.split(/\s+/).filter(t => t.length > 2);
        if (tokens.length === 0) return (await this.listAll()).slice(0, limit);
        
        const searchQuery = tokens.join(' | ');

        const results = await db.select()
            .from(skills)
            .where(sql`search_vector @@ to_tsquery('english', ${searchQuery})`)
            .limit(limit);

        return results.map(this.mapRow);
    }

    public async listAll(): Promise<SkillSummary[]> {
        const results = await db.select().from(skills);
        return results.map(this.mapRow);
    }

    public async inspect(skillRef: string): Promise<SkillSummary | null> {
        const results = await db.select().from(skills).where(eq(skills.skillRef, skillRef));
        if (results.length === 0 || !results[0]) return null;
        return this.mapRow(results[0]);
    }

    private mapRow(row: typeof skills.$inferSelect): SkillSummary {
        const manifest = row.manifest as { bindings: Record<string, string>, fanoutTools: string[] };
        return {
            skillRef: row.skillRef,
            skillId: row.skillId,
            version: row.version,
            description: row.description,
            interfaces: row.interfaces as string[],
            bindings: manifest.bindings,
            fanoutTools: manifest.fanoutTools
        };
    }
}
