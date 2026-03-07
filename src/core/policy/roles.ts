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
import { resolve } from "node:path";
import { getOrgPolicyPaths } from "./org_config";

const DEFAULT_ROLE_FILE_PATH = resolve("policy", "role_permissions.json");

function _loadRolePermissionsFromFile(): Record<string, string[]> {
	// Bun.file(path).json() is async, but we need sync here for the constant export.
	// However, top-level await is supported in Bun modules.
	// But ROLE_PERMISSIONS is exported as a constant.
	// If we want to use Bun.file, we should make this async or use lazy loading.
	// Since this is a config file, maybe we can keep sync read if it's just once at startup?
	// User requested removal of all fs.
	// We can use `await` in module scope.

	// BUT: standard pattern for configs is often sync.
	// Let's refactor ROLE_PERMISSIONS to be a function or promise if strictly no fs.
	// Or we can use Bun.file().json() with await since this is a module.

	// Wait, `loadRolePermissionsFromFile` is called inside `ROLE_PERMISSIONS` definition.
	// If we make it async, `ROLE_PERMISSIONS` becomes a Promise.
	// That breaks the synchronous exports.
	// We should probably change `ROLE_PERMISSIONS` to be loaded asynchronously or lazy.

	// For now, let's keep it sync for simplicity if unavoidable, OR refactor consumer.
	// Consumer `getRolePermissions` is sync. `checkRoleAccess` is sync.
	// Changing this to async ripples everywhere.
	// However, Bun doesn't have a sync file read API that is "native" like Bun.file().
	// Actually, `Bun.file` is lazy, but `text()` returns a Promise.
	// So we MUST be async to use Bun.file.

	// I will refactor `ROLE_PERMISSIONS` to be loaded on demand or cached.
	return {};
}

// Cache by permissions file path
const cachedByPath = new Map<string, Record<string, string[]>>();

async function loadPermissionsFile(
	path: string,
): Promise<Record<string, string[]>> {
	const resolved = resolve(path);
	const cached = cachedByPath.get(resolved);
	if (cached) return cached;

	let parsed: Record<string, string[]> = {};
	try {
		if (await Bun.file(resolved).exists()) {
			parsed = await Bun.file(resolved).json();
		}
	} catch {
		parsed = {};
	}
	cachedByPath.set(resolved, parsed);
	return parsed;
}

export async function getRolePermissionsAsync(
	roles: string[],
	orgId?: string,
): Promise<string[]> {
	const paths = await getOrgPolicyPaths(orgId);
	const filePath = paths.rolePermissionsPath || DEFAULT_ROLE_FILE_PATH;
	const roleMap = await loadPermissionsFile(filePath);

	const permissions = new Set<string>();

	// Add hardcoded defaults
	const defaults: Record<string, string[]> = {
		"mcp:admin": ["*"],
		"mcp:docs-curator": ["skills:docs-to-files@1"],
		"mcp:repo-inspector": ["skills:repo-insight@1"],
	};

	for (const role of roles) {
		// Check defaults
		if (defaults[role]) {
			defaults[role].forEach((p) => {
				permissions.add(p);
			});
		}
		// Check file-loaded
		if (roleMap[role]) {
			roleMap[role].forEach((p) => {
				permissions.add(p);
			});
		}
	}

	return [...permissions];
}

// Synchronous version is deprecated/removed in favor of async to support Bun.file
// But we need to update consumers.
// Let's check usages of `getRolePermissions` and `checkRoleAccess`.
// They are used in `src/agents/main/skill_catalog.ts` and `src/agents/main/discovery.ts`.
// Both are async contexts or can be made async.

export async function checkRoleAccess(
	roles: string[],
	action: string,
	orgId?: string,
): Promise<{ allowed: boolean; matchedPermission?: string; reason?: string }> {
	if (roles.length === 0) {
		return {
			allowed: false,
			reason: "No roles assigned",
		};
	}

	const permissions = await getRolePermissionsAsync(roles, orgId);

	if (permissions.length === 0) {
		return {
			allowed: false,
			reason: `Roles ${roles.join(", ")} have no permissions mapped`,
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
		reason: `Action '${action}' not allowed by roles: ${roles.join(", ")}`,
	};
}

export function matchesPermission(
	permissions: string[],
	action: string,
): boolean {
	for (const perm of permissions) {
		if (matchesPattern(perm, action)) {
			return true;
		}
	}
	return false;
}

// Helper export for sync usage where we accept pre-loaded permissions
export { matchesPermission as matchesPermissionSync };

/**
 * Check if a pattern matches an action.
 */
function matchesPattern(pattern: string, action: string): boolean {
	// Exact match
	if (pattern === action) return true;

	// Global wildcard
	if (pattern === "*") return true;

	// Prefix wildcard: "filesystem.*"
	if (pattern.endsWith(".*")) {
		const prefix = pattern.slice(0, -2);
		return action.startsWith(`${prefix}.`);
	}

	// Suffix wildcard: "*.read_file"
	if (pattern.startsWith("*.")) {
		const suffix = pattern.slice(2);
		return action.endsWith(`.${suffix}`) || action.endsWith(suffix);
	}

	// Glob pattern: "*.search*"
	if (pattern.includes("*")) {
		const regex = new RegExp(
			`^${pattern.replace(/\./g, "\\.").replace(/\*/g, ".*")}$`,
		);
		return regex.test(action);
	}

	return false;
}
