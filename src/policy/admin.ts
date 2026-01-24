import { resolve } from "path";
import type { AbacRuleProposal } from "../skill_creator/types";
import { getOrgPolicyPaths } from "./org_config";
import type { PolicyRule } from "./types";

export interface PolicyFile {
	rules?: PolicyRule[];
}

export async function loadPolicyFile(path: string): Promise<PolicyFile> {
	const resolved = resolve(path);
	if (!(await Bun.file(resolved).exists())) {
		return { rules: [] };
	}
	const raw = await Bun.file(resolved).text();
	const parsed = JSON.parse(raw) as PolicyFile;
	if (!parsed.rules) parsed.rules = [];
	return parsed;
}

export async function savePolicyFile(
	path: string,
	policy: PolicyFile,
): Promise<void> {
	const resolved = resolve(path);
	await Bun.write(
		resolved,
		JSON.stringify({ rules: policy.rules ?? [] }, null, 2),
	);
}

export function proposalToPolicyRule(proposal: AbacRuleProposal): PolicyRule {
	return {
		id: proposal.id,
		action: proposal.action,
		effect: "allow",
		priority: proposal.priority,
		conditions: {
			allowedOrgIds: proposal.conditions.allowedOrgIds,
			allowedTeamIds: proposal.conditions.allowedTeamIds,
		},
	};
}

export async function applyAbacProposalToOrgPolicy(
	proposal: AbacRuleProposal,
	orgId?: string,
): Promise<{ path: string; applied: boolean }> {
	const paths = await getOrgPolicyPaths(orgId);
	const policyPath = paths.policyRulesPath;

	const policy = await loadPolicyFile(policyPath);
	const rules = policy.rules ?? [];

	const next = proposalToPolicyRule(proposal);
	const exists = rules.some((r) => r.id === next.id);
	if (!exists) {
		rules.push(next);
		policy.rules = rules;
		await savePolicyFile(policyPath, policy);
		return { path: policyPath, applied: true };
	}
	return { path: policyPath, applied: false };
}
