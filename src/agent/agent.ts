import { runAgentLoop } from "../agent_loop";
import { analyzeCode } from "../audit";
import type { PolicyEngine } from "../policy/engine";
import { WorkflowRegistry } from "../workflow_registry";
import type { LlmClient } from "./llm_client";
import { buildPrompt } from "./prompt_builder";
import { SkillCatalog } from "./skill_catalog";
import type {
	AgentPromptContext,
	AgentRequest,
	AgentResult,
	AgentSkillDetail,
	AgentSkillSummary,
} from "./types";
import {
	createWorkflowLoopTools,
	type WorkflowLoopState,
} from "./workflow_loop_tools";

export interface AgentOptions {
	llm: LlmClient;
	policy: PolicyEngine;
	model: string;
	temperature?: number;
	maxTokens?: number;
	maxRepairAttempts?: number;
	workflowRegistry?: WorkflowRegistry;
}

export class WorkflowAgent {
	private catalog: SkillCatalog;
	private workflows: WorkflowRegistry;

	constructor(private options: AgentOptions) {
		this.catalog = new SkillCatalog(options.policy);
		this.workflows = options.workflowRegistry ?? new WorkflowRegistry();
	}

	async run(request: AgentRequest): Promise<AgentResult> {
		await this.catalog.refresh();

		const maxSkills = request.maxSkills ?? 5;
		const allowedSkills = await this.catalog.listAllowed(request.identity, 200);

		// Initial static discovery
		let discovered = await this.catalog.search(
			request.goal,
			request.identity,
			maxSkills,
		);
		if (!discovered.length) {
			discovered = allowedSkills.slice(0, maxSkills);
		}

		const currentContext = await this.buildContext(
			discovered,
			request.identity,
			request.goal,
		);
		const prompt = buildPrompt(request.goal, currentContext);
		const loopState: WorkflowLoopState = {
			skills: currentContext.skills,
			workflowExamples: currentContext.workflowExamples ?? [],
			plan: "",
		};
		const loopTools = createWorkflowLoopTools({
			catalog: this.catalog,
			workflows: this.workflows,
			state: loopState,
		});

		const system = `${prompt.system}\n\n[WORKFLOW BUILDER]\nYou can iteratively discover skills and workflow examples before generating final workflow code.\nAlways use skills (L1), never raw tools (L0).\nPrefer asyncio.gather for independent skill calls.`;

		const user = `${prompt.user}\n\nIf you need more skills or examples, call the loop tools (skills.search, skills.get, workflows.search, update_plan).`;

		const { final, iterations } = await runAgentLoop<{
			code: string;
			manifest: { skills: string[]; tools: string[]; io_calls?: string[] };
		}>({
			llm: this.options.llm,
			model: this.options.model,
			system,
			user,
			tools: loopTools,
			toolContext: {
				orgId: request.identity.orgId,
				roles: request.identity.roles,
				scopes: request.identity.scopes,
			},
			options: { maxIterations: 12 },
			validateFinal: async (value) => {
				const code =
					typeof value === "string"
						? value
						: typeof value === "object" && value
							? "code" in value &&
								typeof (value as { code?: unknown }).code === "string"
								? (value as { code: string }).code
								: "result" in value &&
										typeof (value as { result?: unknown }).result ===
											"object" &&
										(value as { result?: unknown }).result &&
										"code" in (value as { result: object }).result &&
										typeof (value as { result: { code?: unknown } }).result
											.code === "string"
									? (value as { result: { code: string } }).result.code
									: undefined
							: undefined;
				if (!code || typeof code !== "string") {
					return {
						ok: false as const,
						error: "final.result must include {code: string}",
					};
				}

				const validation = await this.validateCode(code, {
					skills: loopState.skills,
					selectedSkill: currentContext.selectedSkill,
					workflowExamples: loopState.workflowExamples,
				});
				if (!validation.valid || !validation.manifest) {
					let hint = "";
					if (
						code.includes('skills.load("skills:') ||
						code.includes("skills.load('skills:")
					) {
						hint =
							' Hint: skills.load() must take a plain skill id like skills.load("docs-to-files"), not a skillRef like skills.load("skills:docs-to-files@1").';
					}
					if (code.match(/\w+\.(\w+)\([^=\n]*,[^=\n]*\)/)) {
						hint +=
							" Hint: Prefer keyword arguments when calling skill functions (match the interface signatures).";
					}
					return {
						ok: false as const,
						error: `Gate 1 rejected workflow: ${validation.errors.join("; ")}.${hint}`,
					};
				}

				return {
					ok: true as const,
					value: { code, manifest: validation.manifest },
				};
			},
		});

		await this.workflows.saveWorkflow(
			request.goal,
			final.code,
			final.manifest,
			{
				id: request.identity.roles.join(","),
				orgId: request.identity.orgId,
			},
			request.goal,
		);

		return {
			code: final.code,
			selectedSkills: loopState.skills.map((s) => s.skillRef),
			prompt: `${system}\n\n${user}`,
			repairAttempts: iterations,
			plan: loopState.plan,
			executionGraph: loopState.executionGraph,
		};
	}

	private async buildContext(
		skills: AgentSkillSummary[],
		identity: AgentRequest["identity"],
		goal: string,
	): Promise<AgentPromptContext> {
		const selected = await this.selectSkill(skills, identity);
		const workflowExamples = await this.findWorkflowExamples(
			goal,
			skills,
			identity,
		);
		return {
			skills,
			selectedSkill: selected,
			workflowExamples,
		};
	}

	private async selectSkill(
		skills: AgentSkillSummary[],
		identity: AgentRequest["identity"],
	): Promise<AgentSkillDetail | null> {
		if (!skills.length) return null;
		const chosen = skills[0];
		if (!chosen) return null;
		return await this.catalog.inspect(chosen.skillRef, identity);
	}

	private async findWorkflowExamples(
		goal: string,
		skills: AgentSkillSummary[],
		identity: AgentRequest["identity"],
	): Promise<AgentPromptContext["workflowExamples"]> {
		const allowedSkills = skills.map((skill) => skill.skillRef);
		const results = await this.workflows.search(
			goal,
			allowedSkills,
			identity.orgId,
			3,
		);
		return results.map((entry) => ({
			id: entry.metadata.id,
			goal: entry.metadata.goal,
			summary: entry.metadata.summary,
			skills: entry.metadata.skills,
		}));
	}

	private async validateCode(
		code: string,
		context: AgentPromptContext,
	): Promise<{
		valid: boolean;
		errors: string[];
		manifest?: { skills: string[]; tools: string[]; io_calls?: string[] };
	}> {
		const manifest = await analyzeCode(code);
		const errors = [...manifest.errors];

		const allowedSkills = new Set(
			context.skills.map((skill) => skill.skillRef),
		);
		if (allowedSkills.size) {
			for (const skill of manifest.skills) {
				// Normalize both to check inclusion
				// Skill might be "docs-to-files", allowed might be "skills:docs-to-files@1"
				const skillShort = skill.replace(/^skills:/, "").split("@")[0];

				const isAllowed = Array.from(allowedSkills).some((allowed) => {
					const allowedShort = allowed.replace(/^skills:/, "").split("@")[0];
					return allowed === skill || allowedShort === skillShort;
				});

				if (!isAllowed) {
					errors.push(`Skill '${skill}' not allowed by current context`);
				}
			}
		} else if (manifest.skills.length) {
			errors.push("No skills are available in the current context");
		}

		if (!manifest.skills.length && manifest.tools.length) {
			errors.push("No recognized skills found in code");
		}

		// ... rest of validation logic ...
		const allowedSkillCalls = new Set(
			context.skills.flatMap((skill) => {
				const skillId = skill.skillRef.match(/^skills:([^@]+)@/i)?.[1];
				if (!skillId) return [];
				return skill.interfaces
					.map((signature) => signature.replace(/`/g, "").trim())
					.map((signature) => signature.split("(")[0]?.trim())
					.flatMap((method) => {
						if (!method) return [];
						if (method.includes(".")) {
							return [method];
						}
						return [`${skillId}.${method}`];
					});
			}),
		);

		if (allowedSkillCalls.size) {
			for (const call of manifest.tools) {
				if (!allowedSkillCalls.has(call)) {
					errors.push(`Tool '${call}' not allowed by current context`);
				}
			}
		} else if (manifest.tools.length) {
			errors.push("No tool interfaces are available in the current context");
		}

		const hasAsyncMain = code.includes("async def main");
		if (!hasAsyncMain) {
			errors.push("Code must define 'async def main()'");
		}

		return { valid: errors.length === 0, errors, manifest };
	}
}
