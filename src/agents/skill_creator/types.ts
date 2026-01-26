import type { PolicyEngine } from "../../core/policy/engine";
import type { AbacRuleProposal } from "../../core/policy/types";
import type { ToolDescriptor } from "../../registry/tools";
import type { LlmClient } from "../main/llm_client";

export type { ToolDescriptor }; // Re-export for compatibility

export interface SkillCreatorDependencies {
	llm: LlmClient;
	policy?: PolicyEngine;
}

export interface SkillCreationRequest {
	goal: string;
	constraints?: string[];
	requester: {
		id: string;
		roles: string[];
		orgId?: string;
		teamId?: string;
		sessionId?: string;
		missionId?: string;
	};
}

export interface SkillDraft {
	skillId: string;
	version: number;
	summary: string;
	interfaces: string[];
	bindings: Record<string, string>;
	fanoutTools: string[];
	code: string;
	examples: Array<{
		title?: string;
		description?: string;
		code: string;
	}>;
	dependencies?: string[];
}

export interface SkillCreatorOptions {
	model: string;
	temperature?: number;
	maxTokens?: number;
	maxRepairAttempts?: number;
	toolsPath?: string;
	skillsDir?: string;
	policyFilePath?: string;
	rolePermissionsPath?: string;
}

export type { AbacRuleProposal };

export interface SkillCreationResult {
	skillRef: string;
	skillDir: string;
	draft: SkillDraft;
	rolesGranted: string[];
	orgsGranted: string[];
	teamsGranted: string[];
	abacProposal?: AbacRuleProposal;
}

export interface SkillCreatorSession {
	goal: string;
	constraints: string[];
	selectedTools: ToolDescriptor[];
	draft?: SkillDraft;
	questions: string[];
}

export type SkillCreatorEvent =
	| { type: "question"; message: string }
	| { type: "tool_selection"; tools: ToolDescriptor[] }
	| { type: "draft"; draft: SkillDraft }
	| { type: "complete"; result: SkillCreationResult };
