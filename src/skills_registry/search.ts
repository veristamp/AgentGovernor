import { readFileSync, existsSync, readdirSync } from 'fs';
import { join, resolve } from 'path';
import type { GcmSignature, GcmRegistrySearchResult } from './schema';
import type { SkillSummary, SkillSearchResult } from './registry';
import { SkillRegistry } from './registry';

const DEFAULT_SKILLS_DIR = resolve('skills');

export class GcmRegistrySearch {
    private signatures: GcmSignature[] = [];
    public legacyRegistry: SkillRegistry;

    constructor(private skillsDir: string = DEFAULT_SKILLS_DIR) {
        this.legacyRegistry = new SkillRegistry(skillsDir);
    }

    /**
     * Loads signatures. If signature.json is missing, it auto-compiles from SKILL.md (Migration Layer).
     */
    load(): void {
        const resolved = resolve(this.skillsDir);
        // Ensure legacy registry is loaded for fallback/migration
        this.legacyRegistry.load();
        
        const entries = existsSync(resolved) ? readdirSync(resolved, { withFileTypes: true }) : [];
        this.signatures = [];

        for (const entry of entries) {
            if (!entry.isDirectory()) continue;
            const skillDir = join(resolved, entry.name);
            const sigPath = join(skillDir, 'signature.json');

            if (existsSync(sigPath)) {
                try {
                    const sig = JSON.parse(readFileSync(sigPath, 'utf-8')) as GcmSignature;
                    this.signatures.push(sig);
                } catch (e) {
                    console.error(`Failed to load signature for ${entry.name}:`, e);
                }
            } else {
                // "Just-in-Time Compilation" from Legacy
                const legacySkill = this.legacyRegistry.inspect(`skills:${entry.name}@1`) 
                                 || this.legacyRegistry.listAll().find(s => s.skillId === entry.name);
                
                if (legacySkill) {
                    // Convert Legacy to Signature
                    this.signatures.push({
                        id: `skills.${entry.name}`,
                        version: String(legacySkill.version),
                        description: legacySkill.description.slice(0, 200), // Truncate for efficiency
                        keywords: legacySkill.skillId.split('-'),
                        parameters: {}, // Legacy doesn't have strict param schema easily available without parsing lib.py
                        compute_cost: 'medium',
                        required_policies: [],
                        fanout_tools: legacySkill.fanoutTools
                    });
                }
            }
        }
    }

    /**
     * The Core Search Function (Regex/BM25 style) - Modern Agent Path
     * Mimics tool_search_tool_regex behavior
     */
    search(query: string, limit: number = 5): GcmRegistrySearchResult {
        const q = query.toLowerCase();
        let matches: GcmSignature[] = [];

        try {
            // Regex Mode
            const regex = new RegExp(q, 'i');
            matches = this.signatures.filter(sig => 
                regex.test(sig.id) || 
                regex.test(sig.description) || 
                sig.keywords.some(k => regex.test(k))
            );
        } catch (e) {
            // Fallback to simple inclusion if regex fails
            matches = this.signatures.filter(sig => 
                sig.id.toLowerCase().includes(q) || 
                sig.description.toLowerCase().includes(q)
            );
        }

        // Rank by relevance
        matches.sort((a, b) => {
            if (a.id.includes(q) && !b.id.includes(q)) return -1;
            if (b.id.includes(q) && !a.id.includes(q)) return 1;
            return 0;
        });

        const selected = matches.slice(0, limit);

        return {
            type: 'tool_search_result',
            tool_references: selected.map(sig => ({
                type: 'tool_reference',
                tool_name: sig.id,
                signature: sig
            }))
        };
    }
    
    listAll(): SkillSummary[] {
        return this.legacyRegistry.listAll();
    }
}
