import { SkillRegistry } from '../skills_registry/registry';
import { PolicyEngine } from '../policy/engine';
import { getRolePermissions, matchesPermission } from '../policy/roles';
import type { AgentIdentityScope, AgentSkillDetail, AgentSkillSummary } from './types';

export interface SkillCatalogOptions {
    skillsDir?: string;
}

export class SkillCatalog {
    private registry: SkillRegistry;

    constructor(private policy: PolicyEngine, options?: SkillCatalogOptions) {
        this.registry = new SkillRegistry(options?.skillsDir);
        // Ingest is async, but constructor cannot be.
        // We rely on explicit refresh() or initial load being fast/handled elsewhere if critical.
        // Or we can fire and forget:
        this.registry.ingest().catch(e => console.error("SkillCatalog ingest failed:", e));
    }

    async refresh(): Promise<void> {
        await this.registry.ingest();
    }

    async search(query: string, identity: AgentIdentityScope, limit: number = 10): Promise<AgentSkillSummary[]> {
        const results = await this.registry.search(query, limit);
        return results.filter((skill) => this.isSkillAllowed(skill.skillRef, identity));
    }

    async inspect(skillRef: string, identity: AgentIdentityScope): Promise<AgentSkillDetail | null> {
        if (!this.isSkillAllowed(skillRef, identity)) {
            return null;
        }
        const detail = await this.registry.inspect(skillRef);
        if (!detail) return null;
        return {
            skillRef: detail.skillRef,
            description: detail.description,
            interfaces: detail.interfaces,
            bindings: detail.bindings,
            fanoutTools: detail.fanoutTools,
        };
    }

    async listAllowed(identity: AgentIdentityScope, limit: number = 200): Promise<AgentSkillSummary[]> {
        const all = await this.registry.listAll();
        return all.filter((skill: AgentSkillSummary) => this.isSkillAllowed(skill.skillRef, identity)).slice(0, limit);
    }

    private isSkillAllowed(skillRef: string, identity: AgentIdentityScope): boolean {
        const permissions = getRolePermissions(identity.roles ?? []);
        if (matchesPermission(permissions, '*')) {
            return true;
        }
        if (matchesPermission(permissions, skillRef)) {
            return true;
        }
        const decision = this.policy.check({
            identity: {
                id: 'agent',
                type: 'agent',
                roles: identity.roles ?? [],
                scopes: identity.scopes ?? [],
                orgId: identity.orgId,
            },
            action: skillRef,
        });
        return decision.allowed;
    }
}
