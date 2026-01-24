/**
 * Role-Based Access Control (RBAC) for MCP
 *
 * Maps roles from JWT to tool permissions.
 * The auth server issues coarse-grained roles like "mcp:rag-agent",
 * and this module maps them to fine-grained tool patterns.
 *
 * This decouples the auth server from tool-level authorization.
 */

/**
 * Role to permission mapping.
 * Permissions use glob patterns for skills:
 * - "*" = all skills
 * - "skills:docs-to-files@1" = specific skill version
 */
import { readFileSync, existsSync } from 'fs';
import { resolve } from 'path';

const ROLE_FILE_PATH = resolve('policy', 'role_permissions.json');

function loadRolePermissionsFromFile(): Record<string, string[]> {
    if (!existsSync(ROLE_FILE_PATH)) {
        return {};
    }
    const raw = readFileSync(ROLE_FILE_PATH, 'utf-8');
    const parsed = JSON.parse(raw) as Record<string, string[]>;
    return parsed;
}

export const ROLE_PERMISSIONS: Record<string, string[]> = {
    // Admin - full access
    'mcp:admin': ['*'],

    // Demo roles for skills-only access
    'mcp:docs-curator': [
        'skills:docs-to-files@1',
    ],
    'mcp:repo-inspector': [
        'skills:repo-insight@1',
    ],
    ...loadRolePermissionsFromFile(),
};


/**
 * Expand roles to permissions.
 *
 * @param roles - Array of role strings from JWT
 * @returns Array of permission patterns
 */
export function getRolePermissions(roles: string[]): string[] {
    const permissions = new Set<string>();

    for (const role of roles) {
        const perms = ROLE_PERMISSIONS[role];
        if (perms) {
            perms.forEach((p) => permissions.add(p));
        }
    }

    return [...permissions];
}

/**
 * Check if any permission matches the requested action.
 *
 * @param permissions - Array of permission patterns
 * @param action - The tool action being requested (e.g., "filesystem.read_file")
 * @returns true if any permission matches
 */
export function matchesPermission(permissions: string[], action: string): boolean {
    for (const perm of permissions) {
        if (matchesPattern(perm, action)) {
            return true;
        }
    }
    return false;
}

/**
 * Check if a pattern matches an action.
 *
 * Supports:
 * - Exact match: "filesystem.read_file"
 * - Wildcard all: "*"
 * - Prefix wildcard: "filesystem.*"
 * - Suffix wildcard: "*.read_file"
 * - Glob patterns: "*.search*"
 */
function matchesPattern(pattern: string, action: string): boolean {
    // Exact match
    if (pattern === action) return true;

    // Global wildcard
    if (pattern === '*') return true;

    // Prefix wildcard: "filesystem.*"
    if (pattern.endsWith('.*')) {
        const prefix = pattern.slice(0, -2);
        return action.startsWith(prefix + '.');
    }

    // Suffix wildcard: "*.read_file"
    if (pattern.startsWith('*.')) {
        const suffix = pattern.slice(2);
        return action.endsWith('.' + suffix) || action.endsWith(suffix);
    }

    // Glob pattern: "*.search*"
    if (pattern.includes('*')) {
        const regex = new RegExp(
            '^' + pattern.replace(/\./g, '\\.').replace(/\*/g, '.*') + '$'
        );
        return regex.test(action);
    }

    return false;
}

/**
 * Check if an identity with given roles can perform an action.
 *
 * @param roles - Roles from JWT
 * @param action - Tool action being requested
 * @returns { allowed: boolean, matchedPermission?: string, reason?: string }
 */
export function checkRoleAccess(
    roles: string[],
    action: string
): { allowed: boolean; matchedPermission?: string; reason?: string } {
    if (roles.length === 0) {
        return {
            allowed: false,
            reason: 'No roles assigned',
        };
    }

    const permissions = getRolePermissions(roles);

    if (permissions.length === 0) {
        return {
            allowed: false,
            reason: `Roles ${roles.join(', ')} have no permissions mapped`,
        };
    }

    for (const perm of permissions) {
        if (matchesPattern(perm, action)) {
            return {
                allowed: true,
                matchedPermission: perm,
            };
        }
    }

    return {
        allowed: false,
        reason: `Action '${action}' not allowed by roles: ${roles.join(', ')}`,
    };
}
