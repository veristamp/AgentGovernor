import { resolve } from "node:path";

export interface OrgPolicyPaths {
	policyRulesPath?: string;
	rolePermissionsPath?: string;
	skillGateConfigPath?: string;
}

export interface OrgConfigFile {
	default?: OrgPolicyPaths;
	orgs?: Record<string, OrgPolicyPaths>;
}

const DEFAULT_ORG_CONFIG_PATH = resolve("policy", "org_config.json");

let cached: OrgConfigFile | null = null;

export async function loadOrgConfig(
	path: string = DEFAULT_ORG_CONFIG_PATH,
): Promise<OrgConfigFile> {
	if (cached) return cached;
	try {
		if (await Bun.file(path).exists()) {
			cached = (await Bun.file(path).json()) as OrgConfigFile;
		} else {
			cached = {};
		}
	} catch {
		cached = {};
	}
	return cached;
}

export async function getOrgPolicyPaths(
	orgId?: string,
): Promise<Required<OrgPolicyPaths>> {
	const config = await loadOrgConfig();
	const defaults = config.default ?? {};
	const org =
		orgId && config.orgs && config.orgs[orgId] ? config.orgs[orgId] : {};

	return {
		policyRulesPath: resolve(
			org.policyRulesPath ??
				defaults.policyRulesPath ??
				resolve("policy", "policy_rules.json"),
		),
		rolePermissionsPath: resolve(
			org.rolePermissionsPath ??
				defaults.rolePermissionsPath ??
				resolve("policy", "role_permissions.json"),
		),
		skillGateConfigPath: resolve(
			org.skillGateConfigPath ??
				defaults.skillGateConfigPath ??
				resolve("policy", "skill_gate.json"),
		),
	};
}

export function clearOrgConfigCache(): void {
	cached = null;
}
