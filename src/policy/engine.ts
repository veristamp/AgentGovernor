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

export class PolicyEngine {
    private rules: PolicyRule[] = [];
    private rateLimitCounters: Map<string, { count: number; resetAt: number }> = new Map();

    constructor(rules?: PolicyRule[]) {
        if (rules) {
            this.loadRules(rules);
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
    check(request: PolicyRequest): PolicyDecision {
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

        // 3. Check scope (quick check before full policy eval)
        if (!this.hasScope(identity, action)) {
            return {
                allowed: false,
                reason: `Missing required scope for: ${action}`,
            };
        }

        // 4. Evaluate rules
        for (const rule of this.rules) {
            const match = this.matchesRule(rule, request);
            if (match) {
                // Check conditions
                const conditionResult = this.checkConditions(rule, request);
                if (conditionResult !== true) {
                    if (rule.effect === 'allow') {
                        // Allow rule didn't match conditions - continue to next rule
                        continue;
                    }
                    // Deny rule matched but condition failed - skip
                    continue;
                }

                // Rule matched and conditions passed
                if (rule.effect === 'deny') {
                    return {
                        allowed: false,
                        matchedRule: rule.id,
                        reason: `Denied by rule: ${rule.id}`,
                    };
                }

                // Check rate limit if specified
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

        // Default deny
        return {
            allowed: false,
            reason: 'No matching allow rule found',
        };
    }

    /**
     * Check multiple actions at once (for manifest pre-check).
     */
    checkManifest(identity: Identity, manifest: Manifest): PolicyDecision[] {
        return manifest.tools.map((tool) =>
            this.check({ identity, action: tool })
        );
    }

    /**
     * Quick check if all manifest tools are allowed.
     */
    isManifestAllowed(identity: Identity, manifest: Manifest): { allowed: boolean; violations: string[] } {
        const violations: string[] = [];

        for (const tool of manifest.tools) {
            const decision = this.check({ identity, action: tool });
            if (!decision.allowed) {
                violations.push(`${tool}: ${decision.reason}`);
            }
        }

        return {
            allowed: violations.length === 0,
            violations,
        };
    }

    // ==================== Private Methods ====================

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
