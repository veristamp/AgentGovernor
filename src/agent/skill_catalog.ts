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
        this.registry.load();
    }

    refresh(): void {
        this.registry.load();
    }

    search(query: string, identity: AgentIdentityScope, limit: number = 10): AgentSkillSummary[] {
        const results = this.registry.search(query, limit);
        return results.filter((skill) => this.isSkillAllowed(skill.skillRef, identity));
    }

    inspect(skillRef: string, identity: AgentIdentityScope): AgentSkillDetail | null {
        if (!this.isSkillAllowed(skillRef, identity)) {
            return null;
        }
        const detail = this.registry.inspect(skillRef);
        if (!detail) return null;
        return {
            skillRef: detail.skillRef,
            description: detail.description,
            interfaces: detail.interfaces,
            bindings: detail.bindings,
            fanoutTools: detail.fanoutTools,
        };
    }

    listAllowed(identity: AgentIdentityScope, limit: number = 200): AgentSkillSummary[] {
        const all = this.registry.listAll();
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
