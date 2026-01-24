/**
 * Policy Engine
 * 
 * ABAC (Attribute-Based Access Control) policy engine for Governed Code Mode.
 * Evaluates whether an identity can perform an action on a resource.
 */

import type {
    Identity,
    PolicyRule,
    PolicyDecision,
    PolicyRequest,
    Manifest,
} from './types';
import { checkRoleAccess } from './roles';

export class PolicyEngine {
    private rules: PolicyRule[] = [];
    private rateLimitCounters: Map<string, { count: number; resetAt: number }> = new Map();

    constructor(rules?: PolicyRule[]) {
        if (rules) {
            this.loadRules(rules);
        }
    }

    async loadRulesFromFile(filePath: string): Promise<void> {
        if (!(await Bun.file(filePath).exists())) {
            return;
        }
        const raw = await Bun.file(filePath).text();
        const parsed = JSON.parse(raw) as { rules?: PolicyRule[] };
        if (parsed.rules) {
            this.loadRules(parsed.rules);
        }
    }


    /**
     * Load policy rules. Higher priority rules are evaluated first.
     */
    loadRules(rules: PolicyRule[]): void {
        this.rules = [...rules].sort((a, b) => (b.priority ?? 0) - (a.priority ?? 0));
    }

    /**
     * Add a single rule.
     */
    addRule(rule: PolicyRule): void {
        this.rules.push(rule);
        this.rules.sort((a, b) => (b.priority ?? 0) - (a.priority ?? 0));
    }

    /**
     * Check if an action is allowed.
     */
    async check(request: PolicyRequest): Promise<PolicyDecision> {
        const { identity, action, resource } = request;

        // 1. Check if identity is revoked
        if (identity.revoked) {
            return {
                allowed: false,
                reason: 'Identity has been revoked',
            };
        }

        // 2. Check if JWT is expired
        if (identity.expiresAt && identity.expiresAt < Date.now()) {
            return {
                allowed: false,
                reason: 'Token has expired',
            };
        }

        // 3. Check permission via RBAC (roles) or OAuth scopes
        const hasRbacPermission = await this.hasPermission(identity, action);

        // 4. Evaluate explicit rules (deny rules take precedence)
        for (const rule of this.rules) {
            const match = this.matchesRule(rule, request);
            if (match) {
                // Check conditions
                const conditionResult = this.checkConditions(rule, request);
                if (conditionResult !== true) {
                    continue; // Conditions not met, skip this rule
                }

                // Explicit deny rule - always blocks
                if (rule.effect === 'deny') {
                    return {
                        allowed: false,
                        matchedRule: rule.id,
                        reason: `Denied by rule: ${rule.id}`,
                    };
                }

                // Explicit allow rule - check rate limit and allow
                if (rule.effect === 'allow') {
                    if (rule.conditions?.rateLimit) {
                        const rateLimitResult = this.checkRateLimit(
                            identity.id,
                            action,
                            rule.conditions.rateLimit
                        );
                        if (!rateLimitResult.allowed) {
                            return {
                                allowed: false,
                                matchedRule: rule.id,
                                reason: 'Rate limit exceeded',
                                rateLimit: rateLimitResult.info,
                            };
                        }
                    }

                    return {
                        allowed: true,
                        matchedRule: rule.id,
                    };
                }
            }
        }

        // 5. If RBAC granted permission and no deny rule matched, allow
        if (hasRbacPermission) {
            return {
                allowed: true,
                matchedRule: 'rbac',
                reason: 'Allowed by RBAC roles',
            };
        }

        // Default deny - no RBAC permission and no matching allow rule
        return {
            allowed: false,
            reason: `Missing required permission for: ${action}`,
        };
    }

    /**
     * Check multiple actions at once (for manifest pre-check).
     */
    async checkManifest(identity: Identity, manifest: Manifest): Promise<PolicyDecision[]> {
        return Promise.all(manifest.skills.map((skill) =>
            this.check({ identity, action: skill })
        ));
    }

    /**
     * Quick check if all manifest skills are allowed.
     */
    async isManifestAllowed(identity: Identity, manifest: Manifest): Promise<{ allowed: boolean; violations: string[] }> {
        const violations: string[] = [];

        for (const skill of manifest.skills) {
            const decision = await this.check({ identity, action: skill });
            if (!decision.allowed) {
                violations.push(`${skill}: ${decision.reason}`);
            }
        }

        return {
            allowed: violations.length === 0,
            violations,
        };
    }


    // ==================== Private Methods ====================

    /**
     * Check if identity has permission to perform action.
     * Uses RBAC first (roles -> permissions), then falls back to OAuth scopes.
     */
    private async hasPermission(identity: Identity, action: string): Promise<boolean> {
        // 1. Check RBAC (roles mapped to tool permissions)
        if (identity.roles && identity.roles.length > 0) {
            const rbacResult = await checkRoleAccess(identity.roles, action);
            if (rbacResult.allowed) {
                return true;
            }
        }

        // 2. Fallback to OAuth scopes (for compatibility)
        return this.hasScope(identity, action);
    }

    private hasScope(identity: Identity, action: string): boolean {
        // Check exact match
        if (identity.scopes.includes(action)) {
            return true;
        }

        // Check wildcard patterns
        const parts = action.split('.');
        for (let i = parts.length - 1; i >= 0; i--) {
            const pattern = [...parts.slice(0, i), '*'].join('.');
            if (identity.scopes.includes(pattern)) {
                return true;
            }
        }

        // Check global wildcard
        if (identity.scopes.includes('*')) {
            return true;
        }

        return false;
    }

    private matchesRule(rule: PolicyRule, request: PolicyRequest): boolean {
        const { identity, action, resource } = request;

        // Check identity type
        if (rule.identityTypes && !rule.identityTypes.includes(identity.type)) {
            return false;
        }

        // Check action pattern
        if (!this.matchesPattern(rule.action, action)) {
            return false;
        }

        // Check resource pattern (if specified)
        if (rule.resource && resource) {
            if (!this.matchesPattern(rule.resource, resource)) {
                return false;
            }
        }

        return true;
    }

    private matchesPattern(pattern: string, value: string): boolean {
        if (pattern === '*') return true;
        if (pattern === value) return true;

        // Handle wildcards like "cortex.*"
        if (pattern.endsWith('.*')) {
            const prefix = pattern.slice(0, -2);
            return value.startsWith(prefix + '.');
        }

        // Handle wildcards like "*.search"
        if (pattern.startsWith('*.')) {
            const suffix = pattern.slice(2);
            return value.endsWith('.' + suffix);
        }

        return false;
    }

    private checkConditions(rule: PolicyRule, request: PolicyRequest): true | string {
        const conditions = rule.conditions;
        if (!conditions) return true;

        const { identity } = request;

        // Check security level
        if (conditions.minSecurityLevel !== undefined) {
            const securityLevel = identity.securityLevel ?? 0;
            if (securityLevel < conditions.minSecurityLevel) {
                return `Security level ${securityLevel} < required ${conditions.minSecurityLevel}`;
            }
        }

        if (conditions.maxSecurityLevel !== undefined) {
            const securityLevel = identity.securityLevel ?? 0;
            if (securityLevel > conditions.maxSecurityLevel) {
                return `Security level ${securityLevel} > maximum ${conditions.maxSecurityLevel}`;
            }
        }

        // Check required scopes
        if (conditions.requiredScopes) {
            for (const scope of conditions.requiredScopes) {
                if (!identity.scopes.includes(scope)) {
                    return `Missing required scope: ${scope}`;
                }
            }
        }

        // Check allowed org IDs
        if (conditions.allowedOrgIds && conditions.allowedOrgIds.length > 0) {
            if (!identity.orgId || !conditions.allowedOrgIds.includes(identity.orgId)) {
                return 'Organization not allowed';
            }
        }

        // Check allowed team IDs
        if (conditions.allowedTeamIds && conditions.allowedTeamIds.length > 0) {
            if (!identity.teamId || !conditions.allowedTeamIds.includes(identity.teamId)) {
                return 'Team not allowed';
            }
        }

        // Check time of day
        if (conditions.allowedHours) {
            const hour = new Date().getHours();
            const { start, end } = conditions.allowedHours;
            if (start < end) {
                if (hour < start || hour >= end) {
                    return `Action not allowed at current hour (${hour})`;
                }
            } else {
                // Wraps around midnight
                if (hour < start && hour >= end) {
                    return `Action not allowed at current hour (${hour})`;
                }
            }
        }

        return true;

    }

    private checkRateLimit(
        identityId: string,
        action: string,
        limit: number
    ): { allowed: boolean; info?: { remaining: number; resetAt: number } } {
        const key = `${identityId}:${action}`;
        const now = Date.now();
        const windowMs = 60 * 1000; // 1 minute window

        let counter = this.rateLimitCounters.get(key);

        if (!counter || counter.resetAt <= now) {
            counter = { count: 0, resetAt: now + windowMs };
            this.rateLimitCounters.set(key, counter);
        }

        counter.count++;

        if (counter.count > limit) {
            return {
                allowed: false,
                info: {
                    remaining: 0,
                    resetAt: counter.resetAt,
                },
            };
        }

        return {
            allowed: true,
            info: {
                remaining: limit - counter.count,
                resetAt: counter.resetAt,
            },
        };
    }
}

// ==================== Default Rules ====================

export const DEFAULT_RULES: PolicyRule[] = [
    // Allow all cortex.* for agents with cortex scope
    {
        id: 'allow-cortex-agents',
        identityTypes: ['agent'],
        action: 'cortex.*',
        effect: 'allow',
        priority: 100,
    },
    // Allow search for all authenticated users
    {
        id: 'allow-search-all',
        action: '*.search',
        effect: 'allow',
        priority: 50,
    },
    // Deny dangerous operations by default
    {
        id: 'deny-delete',
        action: '*.delete',
        effect: 'deny',
        priority: 200,
        conditions: {
            minSecurityLevel: 8,
        },
    },
    {
        id: 'deny-write-low-security',
        action: '*.write',
        effect: 'deny',
        priority: 150,
        conditions: {
            maxSecurityLevel: 5,
        },
    },
    // Rate limit heavy operations
    {
        id: 'rate-limit-ingest',
        action: 'cortex.ingest',
        effect: 'allow',
        priority: 100,
        conditions: {
            rateLimit: 10, // 10 per minute
        },
    },
];
