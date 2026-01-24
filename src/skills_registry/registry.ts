import { readFileSync, existsSync, readdirSync } from 'fs';
import { join, resolve } from 'path';

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

function readManifest(skillDir: string): { skillId: string; version: string; bindings: Record<string, string>; fanoutTools: string[] } | null {
    const manifestPath = join(skillDir, 'manifest.json');
    if (!existsSync(manifestPath)) return null;
    const raw = readFileSync(manifestPath, 'utf-8');
    const data = JSON.parse(raw) as {
        skillId?: string;
        version?: number | string;
        bindings?: Record<string, string>;
        fanoutTools?: string[];
    };
    const skillId = String(data.skillId ?? '').trim();
    const version = String(data.version ?? 1);
    const bindings = data.bindings ?? {};
    const fanoutTools = Array.isArray(data.fanoutTools) ? data.fanoutTools : [];
    if (!skillId) return null;
    return { skillId, version, bindings, fanoutTools };
}

function readSkillDoc(skillDir: string): { description: string; interfaces: string[] } {
    const skillDocPath = join(skillDir, 'SKILL.md');
    if (!existsSync(skillDocPath)) {
        return { description: '', interfaces: [] };
    }

    const lines = readFileSync(skillDocPath, 'utf-8').split(/\r?\n/);
    let description = '';
    const interfaces: string[] = [];
    let inInterfaceSection = false;

    for (const line of lines) {
        const trimmed = line.trim();
        if (!description && trimmed && !trimmed.startsWith('#') && !trimmed.startsWith('-')) {
            description = trimmed;
        }
        if (trimmed.toLowerCase() === '## interface') {
            inInterfaceSection = true;
            continue;
        }
        if (inInterfaceSection) {
            if (trimmed.startsWith('## ')) {
                inInterfaceSection = false;
                continue;
            }
            if (trimmed.startsWith('-')) {
                interfaces.push(trimmed.replace(/^[-\s]+/, ''));
            }
        }
    }

    return { description, interfaces };
}

export class SkillRegistry {
    private skills: SkillSummary[] = [];

    constructor(private skillsDir: string = DEFAULT_SKILLS_DIR) {}

    load(): void {
        const resolved = resolve(this.skillsDir);
        const entries = existsSync(resolved) ? readdirSync(resolved, { withFileTypes: true }) : [];
        this.skills = [];

        for (const entry of entries) {
            if (!entry.isDirectory()) continue;
            const skillDir = join(resolved, entry.name);
            const manifest = readManifest(skillDir);
            if (!manifest) continue;

            const doc = readSkillDoc(skillDir);
            const skillRef = `skills:${manifest.skillId}@${manifest.version}`;

            this.skills.push({
                skillRef,
                skillId: manifest.skillId,
                version: manifest.version,
                description: doc.description,
                interfaces: doc.interfaces,
                bindings: manifest.bindings,
                fanoutTools: manifest.fanoutTools,
            });
        }
    }

    search(query: string, limit: number = 20): SkillSearchResult[] {
        const q = query.trim().toLowerCase();
        const results: SkillSearchResult[] = [];

        for (const skill of this.skills) {
            if (!q || q === '*') {
                results.push({
                    skillRef: skill.skillRef,
                    description: skill.description,
                    interfaces: skill.interfaces,
                    bindings: skill.bindings,
                    fanoutTools: skill.fanoutTools,
                });
                if (results.length >= limit) break;
                continue;
            }

            const haystack = [
                skill.skillRef,
                skill.skillId,
                skill.description,
                ...skill.interfaces,
            ]
                .join(' ')
                .toLowerCase();

            if (haystack.includes(q)) {
                results.push({
                    skillRef: skill.skillRef,
                    description: skill.description,
                    interfaces: skill.interfaces,
                    bindings: skill.bindings,
                    fanoutTools: skill.fanoutTools,
                });
                if (results.length >= limit) break;
            }
        }

        return results;
    }

    listAll(): SkillSummary[] {
        return [...this.skills];
    }

    inspect(skillRef: string): SkillSummary | null {
        return this.skills.find((skill) => skill.skillRef === skillRef) ?? null;
    }
}
