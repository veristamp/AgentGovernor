/**
 * Policy Types
 *
 * Types for the ABAC (Attribute-Based Access Control) policy engine.
 */

/** Identity information from JWT */
export interface Identity {
	/** Unique identity ID (e.g., "mcp_xxx", "user:456") */
	id: string;
	/** Type of identity */
	type: "agent" | "user" | "service";
	/** Roles from JWT (e.g., "mcp:rag-agent", "mcp:admin") */
	roles: string[];
	/** Scopes granted to this identity (OAuth2 scope claim) */
	scopes: string[];
	/** Organization/tenant ID */
	orgId?: string;
	/** Team ID within an org */
	teamId?: string;
	/** Security level (0-10) - optional, defaults to 0 */
	securityLevel?: number;
	/** Whether identity has been revoked */
	revoked?: boolean;
	/** JWT expiration timestamp */
	expiresAt?: number;
}

/** A policy rule */
export interface PolicyRule {
	/** Rule ID for debugging */
	id: string;
	/** Identity types this rule applies to */
	identityTypes?: ("agent" | "user" | "service")[];
	/** Action/tool pattern (supports wildcards: "cortex.*") */
	action: string;
	/** Resource pattern (supports wildcards) */
	resource?: string;
	/** Effect: allow or deny */
	effect: "allow" | "deny";
	/** Conditions that must be met */
	conditions?: PolicyConditions;
	/** Priority (higher = evaluated first) */
	priority?: number;
}

/** Conditions for policy evaluation */
export interface PolicyConditions {
	/** Minimum security level required */
	minSecurityLevel?: number;
	/** Maximum security level allowed */
	maxSecurityLevel?: number;
	/** Required scopes (all must be present) */
	requiredScopes?: string[];
	/** Organization must match */
	orgMatch?: boolean;
	/** Allowed org IDs */
	allowedOrgIds?: string[];
	/** Allowed team IDs */
	allowedTeamIds?: string[];
	/** Time-of-day restrictions (24h format) */
	allowedHours?: { start: number; end: number };
	/** Rate limit (calls per minute) */
	rateLimit?: number;
}

/** Result of policy evaluation */
export interface PolicyDecision {
	/** Whether the action is allowed */
	allowed: boolean;
	/** Rule that matched (if any) */
	matchedRule?: string;
	/** Reason for denial (if denied) */
	reason?: string;
	/** Rate limit info (if applicable) */
	rateLimit?: {
		remaining: number;
		resetAt: number;
	};
}

/** Manifest from static auditor */
export interface Manifest {
	tools: string[];
	skills: string[];
	toolCalls: Array<{
		tool: string;
		line: number;
		col: number;
		staticArgs: Record<string, unknown>;
		dynamicArgs: string[];
	}>;
	hasLoops: boolean;
	hasConditionals: boolean;
	maxDepth: number;
	errors: string[];
	warnings: string[];
}

/** Policy check request */
export interface PolicyRequest {
	identity: Identity;
	action: string;
	resource?: string;
	args?: Record<string, unknown>;
}
