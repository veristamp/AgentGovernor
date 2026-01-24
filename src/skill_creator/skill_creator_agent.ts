import { mkdir } from "node:fs/promises";
import { join, resolve } from "path";

import type { LlmClient } from "../agent/llm_client";
import { analyzeSkillCode } from "../audit";
import { getOrgPolicyPaths } from "../policy/org_config";
import type {
	SkillExample,
	SkillFunctionSignature,
} from "../skills_registry/schema";
import {
	buildGenerationPrompt,
	buildRepairPrompt,
	buildSelectionPrompt,
	type SkillDraftResponse,
	type ToolSelectionResponse,
} from "./prompt_builder";
import {
	expandTools,
	loadTools,
	retrieveRelevantTools,
} from "./tool_retriever";
import type {
	AbacRuleProposal,
	SkillCreationRequest,
	SkillCreationResult,
	SkillCreatorDependencies,
	SkillCreatorEvent,
	SkillCreatorOptions,
	SkillDraft,
	ToolDescriptor,
} from "./types";

export class SkillCreatorAgent {
	private llm: LlmClient;
	private options: SkillCreatorOptions;

	constructor(
		dependencies: SkillCreatorDependencies,
		options: SkillCreatorOptions,
	) {
		this.options = options;
		this.llm = dependencies.llm;
	}

	async run(
		request: SkillCreationRequest,
		onEvent?: (event: SkillCreatorEvent) => void,
	): Promise<SkillCreationResult> {
		// ========================================================================
		// Phase 1: Tool Discovery & Selection (Interactive Loop)
		// ========================================================================

		const candidateTools = await retrieveRelevantTools(
			request.goal,
			request.constraints || [],
			{ toolsPath: this.options.toolsPath },
			15,
		);

		const allTools = await loadTools(this.options.toolsPath);
		let finalSelection: ToolSelectionResponse | undefined;
		let discoveryAttempts = 0;
		const maxDiscoveryAttempts = 3;

		// Loop until LLM is satisfied with toolset
		while (discoveryAttempts < maxDiscoveryAttempts) {
			discoveryAttempts++;
			if (onEvent) onEvent({ type: "tool_selection", tools: candidateTools });

			// Ask LLM to select or request more
			const selection = await this.performToolSelection(
				request.goal,
				candidateTools,
				request.constraints || [],
			);

			// Always track the latest selection as a fallback
			finalSelection = selection;

			// Check for missing capabilities
			if (
				selection.missing_capabilities &&
				selection.missing_capabilities.length > 0
			) {
				console.log(
					`[SkillCreator] LLM requested missing capabilities: ${selection.missing_capabilities.join(", ")}`,
				);

				// Search for missing tools
				const newTools: ToolDescriptor[] = [];
				for (const query of selection.missing_capabilities) {
					const found = await retrieveRelevantTools(
						query,
						[],
						{ toolsPath: this.options.toolsPath },
						5,
					);
					newTools.push(...found);
				}

				// Merge unique new tools into candidates
				const beforeCount = candidateTools.length;
				for (const tool of newTools) {
					if (
						!candidateTools.find((t) => t.qualifiedName === tool.qualifiedName)
					) {
						candidateTools.push(tool);
					}
				}

				if (candidateTools.length === beforeCount) {
					console.log(
						"[SkillCreator] No new tools found for missing capabilities. Proceeding with best effort.",
					);
					finalSelection = selection;
					break;
				}

				// Continue loop with expanded candidates
				continue;
			}

			// No missing capabilities, we are done with Phase 1
			finalSelection = selection;
			break;
		}

		if (!finalSelection) {
			throw new Error("Failed to select tools.");
		}

		// 3. Resolve selected tools to full descriptors with schemas
		let selectedDescriptors: ToolDescriptor[] = [];

		for (const name of finalSelection.selected_tools) {
			const found =
				candidateTools.find((t) => t.qualifiedName === name) ||
				allTools.find((t) => t.qualifiedName === name);

			if (found) {
				selectedDescriptors.push(found);
			} else {
				console.warn(
					`[SkillCreator] Warning: Selected tool '${name}' not found.`,
				);
			}
		}

		if (selectedDescriptors.length === 0) {
			console.warn(
				"[SkillCreator] No tools selected. Falling back to top 10 candidates.",
			);
			console.log(
				"[SkillCreator] Candidates were:",
				candidateTools.map((t) => t.qualifiedName).join(", "),
			);
			selectedDescriptors = candidateTools.slice(0, 10);
		}

		if (onEvent)
			onEvent({ type: "tool_selection", tools: selectedDescriptors });

		// ========================================================================
		// Phase 2: Skill Generation (Implementation)
		// ========================================================================

		let attempts = 0;
		const maxAttempts = 3;

		while (attempts < maxAttempts) {
			attempts++;

			// 4. Build Generation Prompt with Schemas
			const plan = finalSelection.execution_graph
				? `${finalSelection.reasoning}\n\nEXECUTION_GRAPH:\n${JSON.stringify(finalSelection.execution_graph, null, 2)}`
				: finalSelection.reasoning;
			const { system, user } = buildGenerationPrompt(
				request.goal,
				selectedDescriptors,
				plan,
			);

			// 5. Call LLM
			const responseText = await this.llm.complete(
				[
					{ role: "system", content: system },
					{ role: "user", content: user },
				],
				{
					model: this.options.model,
					temperature: this.options.temperature,
					maxTokens: this.options.maxTokens,
				},
			);

			// 6. Parse & Repair Loop
			let draft: SkillDraftResponse | undefined;
			draft = await this.parseAndRepair(responseText);

			if (!draft) {
				throw new Error("Failed to parse LLM response after repairs");
			}

			// 7. Validate: Check if used tools match selected tools
			const usedTools = draft.fanout_tools || [];
			const missingTools = usedTools.filter(
				(t) => !selectedDescriptors.find((sd) => sd.qualifiedName === t),
			);

			if (missingTools.length > 0) {
				console.log(
					`[SkillCreator] Generation used unselected tools: ${missingTools.join(", ")}. Retrying...`,
				);

				// Add missing tools to context if they exist
				for (const missing of missingTools) {
					const found = allTools.find((t) => t.qualifiedName === missing);
					if (found) selectedDescriptors.push(found);
				}
				continue;
			}

			// 8. Success - Create Skill
			const skillDraft: SkillDraft = {
				skillId: draft.skill_id,
				version: 1,
				summary: draft.summary,
				interfaces: Array.isArray(draft.interface)
					? draft.interface
					: draft.interface
						? [String(draft.interface)]
						: [],
				bindings: draft.bindings || {},
				fanoutTools: draft.fanout_tools || [],
				code: draft.code,
				examples: Array.isArray(draft.examples) ? draft.examples : [],
				dependencies: Array.isArray(draft.dependencies)
					? draft.dependencies
					: [],
			};

			if (onEvent) onEvent({ type: "draft", draft: skillDraft });

			return await this.finalizeSkill(skillDraft, request);
		}

		throw new Error("Max attempts reached without successful skill creation");
	}

	private async performToolSelection(
		goal: string,
		candidates: ToolDescriptor[],
		constraints: string[],
	): Promise<ToolSelectionResponse> {
		const { system, user } = buildSelectionPrompt(
			goal,
			candidates,
			constraints,
		);

		const responseText = await this.llm.complete(
			[
				{ role: "system", content: system },
				{ role: "user", content: user },
			],
			{
				model: this.options.model,
				temperature: 0.2, // Low temp for planning
				maxTokens: 1024,
			},
		);

		const parsed =
			await this.parseAndRepair<ToolSelectionResponse>(responseText);
		if (!parsed) {
			// Fallback: Select all candidates if parsing fails? Or fail?
			return {
				reasoning: "Failed to parse plan, using default.",
				selected_tools: candidates.slice(0, 5).map((t) => t.qualifiedName),
				missing_capabilities: [],
				questions: [],
			};
		}
		return parsed;
	}

	private async parseAndRepair<T>(
		responseText: string,
	): Promise<T | undefined> {
		let attempts = 0;
		const maxRepair = this.options.maxRepairAttempts || 3;

		while (attempts < maxRepair) {
			try {
				const jsonMatch =
					responseText.match(/```json\n([\s\S]*?)\n```/) ||
					responseText.match(/```\n([\s\S]*?)\n```/);
				const jsonStr = jsonMatch ? jsonMatch[1] : responseText;

				if (jsonStr) {
					return JSON.parse(jsonStr) as T;
				}
			} catch (e) {
				attempts++;
				console.warn(
					`[SkillCreator] JSON parse failed, repairing (${attempts}/${maxRepair})...`,
				);

				const repair = buildRepairPrompt(responseText);
				responseText = await this.llm.complete(
					[
						{ role: "system", content: repair.system },
						{ role: "user", content: repair.user },
					],
					{
						model: this.options.model,
						temperature: 0,
					},
				);
			}
		}
		return undefined;
	}

	private async finalizeSkill(
		draft: SkillDraft,
		request: SkillCreationRequest,
	): Promise<SkillCreationResult> {
		const paths = await getOrgPolicyPaths(request.requester.orgId);
		const audit = await analyzeSkillCode(draft.code, {
			configPath: paths.skillGateConfigPath,
		});
		if (!audit.allowed) {
			throw new Error(
				`Skill gate rejected ${draft.skillId}: ${audit.errors.join("; ")}`,
			);
		}
		const skillsDir = this.options.skillsDir || resolve("skills");
		const skillPath = join(skillsDir, draft.skillId);

		// 1. Create directory
		await mkdir(skillPath, { recursive: true });

		// 2. Write files
		await Bun.write(
			join(skillPath, "manifest.json"),
			JSON.stringify(
				{
					skillId: draft.skillId,
					version: draft.version,
					description: draft.summary,
					interfaces: draft.interfaces,
					bindings: draft.bindings,
					fanoutTools: draft.fanoutTools,
					ownerOrgId: request.requester.orgId,
					ownerTeamId: request.requester.teamId,
					createdBy: request.requester.id,
					visibility: request.requester.orgId ? "org" : "private",
				},
				null,
				2,
			),
		);

		const examplesSection = this.formatExamplesMarkdown(
			draft.examples,
			draft.skillId,
			draft.interfaces,
		);
		await Bun.write(
			join(skillPath, "SKILL.md"),
			`# ${draft.skillId}\n\n${draft.summary}\n\n## Interface\n\n\`\`\`python\n${draft.interfaces.join("\n")}\n\`\`\`\n\n${examplesSection}`,
		);

		await Bun.write(join(skillPath, "lib.py"), draft.code);

		const functions = this.buildFunctionSignatures(draft.interfaces);
		const examples = this.ensureExamples(
			draft.examples,
			draft.skillId,
			draft.interfaces,
		);
		await Bun.write(
			join(skillPath, "signature.json"),
			JSON.stringify(
				{
					skillRef: `skills:${draft.skillId}@${draft.version}`,
					skillId: draft.skillId,
					version: String(draft.version),
					description: draft.summary,
					keywords: draft.skillId.split("-").filter(Boolean),
					functions,
					examples,
					dependencies: draft.dependencies ?? [],
				},
				null,
				2,
			),
		);

		// 3. Update RBAC
		const rolePermissionsPath =
			this.options.rolePermissionsPath ||
			resolve("policy", "role_permissions.json");
		await this.updateRbac(
			rolePermissionsPath,
			request.requester.roles,
			draft.skillId,
			draft.version,
		);

		// 4. Create ABAC Proposal
		const abacProposal: AbacRuleProposal = {
			id: `allow-${draft.skillId}-${Date.now()}`,
			action: `skills:${draft.skillId}@${draft.version}`,
			conditions: {
				allowedOrgIds: request.requester.orgId
					? [request.requester.orgId]
					: undefined,
				allowedTeamIds: request.requester.teamId
					? [request.requester.teamId]
					: undefined,
			},
			priority: 10,
		};

		return {
			skillRef: `skills:${draft.skillId}@${draft.version}`,
			skillDir: skillPath,
			draft,
			rolesGranted: request.requester.roles,
			orgsGranted: request.requester.orgId ? [request.requester.orgId] : [],
			teamsGranted: request.requester.teamId ? [request.requester.teamId] : [],
			abacProposal,
		};
	}

	private buildFunctionSignatures(
		interfaces: string[],
	): SkillFunctionSignature[] {
		return interfaces.map((signature) => {
			const cleaned = signature.replace(/^async\s+def\s+/i, "").trim();
			const name = cleaned.split("(")[0]?.trim() || cleaned;
			const paramsSection = cleaned.includes("(")
				? cleaned.slice(cleaned.indexOf("(") + 1, cleaned.lastIndexOf(")"))
				: "";
			const params = paramsSection
				.split(",")
				.map((param) => param.trim())
				.filter(Boolean)
				.map((param) => {
					const beforeDefault = param.split("=")[0]?.trim() ?? "";
					const paramName = beforeDefault.split(":")[0]?.trim() ?? "";
					return {
						name: paramName || "param",
						type: "any" as const,
						required: !param.includes("="),
					};
				})
				.filter((param) => param.name !== "param");
			return {
				name,
				params,
			};
		});
	}

	private ensureExamples(
		examples: SkillExample[],
		skillId: string,
		interfaces: string[],
	): SkillExample[] {
		if (examples.length) {
			return examples;
		}
		const method =
			interfaces[0]
				?.split("(")[0]
				?.replace(/^async\s+def\s+/i, "")
				.trim() || "method";
		return [
			{
				title: `Use ${skillId}`,
				code: `import skills\n\nasync def main():\n    result = await skills.load("${skillId}").${method}(...)\n    return result\n`,
			},
		];
	}

	private formatExamplesMarkdown(
		examples: SkillExample[],
		skillId: string,
		interfaces: string[],
	): string {
		const rendered = this.ensureExamples(examples, skillId, interfaces);
		const blocks = rendered.map((example) => {
			const title = example.title ? `### ${example.title}\n\n` : "";
			const description = example.description
				? `${example.description}\n\n`
				: "";
			return `${title}${description}\`\`\`python\n${example.code.trim()}\n\`\`\``;
		});
		return `## Examples\n\n${blocks.join("\n\n")}`;
	}

	private async updateRbac(
		path: string,
		roles: string[],
		skillId: string,
		version: number,
	) {
		let rbac: Record<string, string[]> = {};
		if (await Bun.file(path).exists()) {
			const content = await Bun.file(path).text();
			rbac = JSON.parse(content);
		}

		const skillRef = `skills:${skillId}@${version}`;
		let updated = false;

		for (const role of roles) {
			if (!rbac[role]) {
				rbac[role] = [];
			}
			if (!rbac[role].includes(skillRef)) {
				rbac[role].push(skillRef);
				updated = true;
			}
		}

		if (updated) {
			await Bun.write(path, JSON.stringify(rbac, null, 2));
		}
	}
}
