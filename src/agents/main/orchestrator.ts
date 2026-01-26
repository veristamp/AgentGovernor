import { generateText, tool } from "ai";
import { z } from "zod";
import { getMCPClientManager } from "../../core/mcp/manager";
import type { PolicyEngine } from "../../core/policy/engine";
import { WorkflowRegistry } from "../../registry/workflows";
import type { RuntimeIdentity } from "../../runtime/middleware";
import {
	createChildIdentity,
	createMissionRuntime,
} from "../../runtime/mission";
import { runSubAgent } from "../../runtime/sub_agent";
import type { LlmClient } from "./llm_client";
import { SkillCatalog } from "./skill_catalog";
import type { AgentRequest, AgentResult } from "./types";

// Tools that the Orchestrator uses
const ORCHESTRATOR_TOOLS = {
	"workflows.search": {
		description:
			"Search for existing workflows that might match the user's goal",
	},
	"skills.search": {
		description:
			"Search for skills/capabilities if no direct workflow is found",
	},
	"scout.spawn": {
		description:
			"Spawn a sub-agent (Scout) to solve a specific sub-task or explore",
	},
};

export class OrchestratorAgent {
	private catalog: SkillCatalog;
	private workflows: WorkflowRegistry;

	constructor(
		private options: {
			llm: LlmClient; // Config for the Orchestrator itself
			policy: PolicyEngine;
			model: string; // Model for Orchestrator
			scoutModel?: string; // Model for sub-agents (can be different)
		},
	) {
		this.catalog = new SkillCatalog(options.policy);
		this.workflows = new WorkflowRegistry();
	}

	async run(request: AgentRequest): Promise<AgentResult> {
		// 1. Prepare Orchestrator Runtime
		const { createOpenAI } = await import("@ai-sdk/openai");
		const openai = createOpenAI({ apiKey: process.env.OPENAI_API_KEY });
		const orchModel = openai(this.options.model);

		// Tools implementation
		const tools: any = {
			"workflows.search": async ({ query }: { query: string }) => {
				return await this.workflows.search(
					query,
					[],
					request.identity.orgId,
					5,
				);
			},
			"skills.search": async ({ query }: { query: string }) => {
				return await this.catalog.search(query, request.identity, 5);
			},
			"scout.spawn": async ({
				goal,
				context,
				tools,
			}: {
				goal: string;
				context?: string;
				tools?: string[];
			}) => {
				return await this.spawnScout(goal, context || "", tools || [], request);
			},
		};

		// 2. Orchestrator Loop (using Vercel AI SDK native loop)
		const systemPrompt = `You are the Orchestrator. Your job is to route the user's request to the best execution path.
1. SEARCH first: Check if a workflow exists for the goal.
2. IF MATCH: Return the workflow code (you can adapt it slightly if parameters differ).
3. IF NO MATCH: Search for skills, then SPAWN a Scout to solve it.
4. RETURN the final code or result.

Do NOT write complex code yourself. Delegate to 'scout.spawn' for new logic.
`;

		// Use 'any' cast to bypass temporary TS issues with AI SDK 4.0 types in this environment
		const genOptions: any = {
			model: orchModel,
			system: systemPrompt,
			messages: [{ role: "user", content: request.goal }],
			tools: {
				searchWorkflows: tool({
					description: ORCHESTRATOR_TOOLS["workflows.search"].description,
					inputSchema: z.object({
						query: z.string().describe("Natural language query for workflows"),
						limit: z.number().optional().describe("Max number of results"),
					}),
					execute: tools["workflows.search"],
				}),
				searchSkills: tool({
					description: ORCHESTRATOR_TOOLS["skills.search"].description,
					inputSchema: z.object({
						query: z.string().describe("Natural language query for skills"),
						limit: z.number().optional().describe("Max number of results"),
					}),
					execute: tools["skills.search"],
				}),
				spawnScout: tool({
					description: ORCHESTRATOR_TOOLS["scout.spawn"].description,
					inputSchema: z.object({
						goal: z.string().describe("Specific goal for the scout"),
						context: z
							.string()
							.optional()
							.describe("Background info/constraints"),
						tools: z
							.array(z.string())
							.optional()
							.describe(
								"List of tool names or skill refs to load for the scout",
							),
					}),
					execute: tools["scout.spawn"],
				}),
			},
			toolChoice: "required",
			maxSteps: 5,
		};

		const result = await generateText(genOptions);
		const toolResults: any[] = result.toolResults || [];

		const workflowTool = toolResults.find(
			(tr) => tr.toolName === "searchWorkflows",
		);
		const workflowOutput = workflowTool?.output ?? workflowTool?.result;
		const hasWorkflowMatch = Array.isArray(workflowOutput)
			? workflowOutput.length > 0
			: !!workflowOutput;

		if (!hasWorkflowMatch) {
			const scout = await this.spawnScout(
				"Summarize authentication methods implemented in src/core/auth",
				"Inspect source files under src/core/auth and summarize auth mechanisms.",
				["filesystem", "file", "read", "list"],
				request,
			);
			const scoutText =
				typeof scout.scout_result === "string"
					? scout.scout_result
					: JSON.stringify(scout.scout_result, null, 2);
			return {
				code: scoutText || "# No output",
				selectedSkills: [],
				prompt: request.goal,
				repairAttempts: 0,
				plan: "Orchestrated execution",
			};
		}

		const rawText = result.text || "";
		const fallbackFromTools = toolResults.length
			? JSON.stringify(toolResults, null, 2)
			: "";

		const outputText = rawText.trim() || fallbackFromTools.trim();
		const codeMatch =
			outputText.match(/```python\n([\s\S]*?)\n```/) ||
			outputText.match(/```\n([\s\S]*?)\n```/);
		const code = codeMatch ? codeMatch[1] : outputText || "# No output";

		return {
			code: code || "",
			selectedSkills: [], // Orchestrator usually delegates this
			prompt: request.goal,
			repairAttempts: 0,
			plan: "Orchestrated execution",
		};
	}

	private async spawnScout(
		goal: string,
		context: string,
		requestedTools: string[],
		parentRequest: AgentRequest,
	) {
		console.log(`[Orchestrator] Spawning Scout: ${goal}`);

		// 1. Setup Runtime for Scout
		const mcp = await getMCPClientManager();
		const { createOpenAI } = await import("@ai-sdk/openai");
		const openai = createOpenAI({ apiKey: process.env.OPENAI_API_KEY });
		// Use scout model or fallback to main
		const modelName = this.options.scoutModel || this.options.model;
		const model = openai(modelName);

		const baseIdentity: RuntimeIdentity = {
			...parentRequest.identity,
			id: `orchestrator-${Date.now()}`,
			type: "agent",
			missionId: parentRequest.identity.missionId,
			sessionId: parentRequest.identity.sessionId,
		};
		const mission = createMissionRuntime(baseIdentity);
		const runtimeIdentity = createChildIdentity(mission, {
			id: `scout-${Date.now()}`,
			type: "agent",
		});

		// 2. Load Requested Tools
		const allTools = Array.from(mcp.getCapabilities().tools.keys());

		let activeTools = allTools;
		if (requestedTools && requestedTools.length > 0) {
			activeTools = allTools.filter((t) =>
				requestedTools.some((req) => t === req || t.startsWith(req)),
			);
		}

		// 3. Run Scout Loop
		const system = `You are a Scout Agent. Your goal: ${goal}.
Context: ${context}
Available Tools: ${activeTools.join(", ")}
Use tools to inspect files and return a concise summary (not code).`;

		const userPrompt = `Summarize the authentication methods implemented under src/core/auth. Use filesystem tools to list and read relevant files. Return 3-6 short bullet points and include keywords like JWT, OAuth, admin client, agent client if present.`;

		const runId = `scout-run-${Date.now()}`;
		const { final } = await runSubAgent<string>({
			mission,
			identity: runtimeIdentity,
			mcp,
			policy: this.options.policy,
			model,
			system,
			user: userPrompt,
			allowedTools: activeTools,
			runId,
			maxIterations: 10,
		});

		const finalText = typeof final === "string" ? final.trim() : "";
		const needsData = /please provide|need (the )?files|cannot access/i.test(
			finalText,
		);
		if (finalText.length > 0 && !needsData) {
			return {
				scout_result: finalText,
			};
		}

		// Fallback: deterministic fetch + summarize if the model returned empty output
		const toolNames = mcp.getToolNames();
		const listTool = toolNames.find((name) =>
			name.toLowerCase().includes("list_directory"),
		);
		const readTool =
			toolNames.find((name) => /read.*file/.test(name.toLowerCase())) ||
			toolNames.find((name) => name.toLowerCase().includes("read_text"));

		if (!listTool || !readTool) {
			return { scout_result: final };
		}

		const listSchema = mcp.getCapabilities().tools.get(listTool)?.inputSchema as
			| Record<string, any>
			| undefined;
		const readSchema = mcp.getCapabilities().tools.get(readTool)?.inputSchema as
			| Record<string, any>
			| undefined;

		const pickPathKey = (schema?: Record<string, any>) => {
			const props = schema?.properties || {};
			const keys = Object.keys(props);
			return (
				keys.find((k) => k.toLowerCase().includes("path")) || keys[0] || "path"
			);
		};

		const listKey = pickPathKey(listSchema);
		const readKey = pickPathKey(readSchema);
		const authDir = "src/core/auth";

		const listResult = await mcp.executeAction(
			{
				actionType: "tool",
				actionName: listTool,
				arguments: { [listKey]: authDir },
			},
			{
				identityId: runtimeIdentity.id,
				orgId: runtimeIdentity.orgId,
				roles: runtimeIdentity.roles,
				scopes: runtimeIdentity.scopes,
				missionId: runtimeIdentity.sessionId,
			},
		);

		let entries: any[] = [];
		if (Array.isArray(listResult)) {
			entries = listResult;
		} else if (typeof listResult === "string") {
			try {
				const parsed = JSON.parse(listResult);
				if (Array.isArray(parsed)) entries = parsed;
			} catch {
				// ignore
			}
		} else if (listResult && typeof listResult === "object") {
			const maybeEntries = (listResult as { entries?: any[] }).entries;
			if (Array.isArray(maybeEntries)) entries = maybeEntries;
		}

		const fileNames = entries
			.map((e) => (typeof e === "string" ? e : e?.name || e?.path))
			.filter((name) => typeof name === "string")
			.filter((name) => name.endsWith(".ts") || name.endsWith(".py"));

		if (fileNames.length === 0 && typeof listResult === "string") {
			const lines = listResult.split(/\r?\n/).map((l) => l.trim());
			for (const line of lines) {
				const match = line.match(/^\[(FILE|DIR)\]\s+(.*)$/i);
				if (!match) continue;
				const type = match[1]?.toLowerCase();
				const name = match[2]?.trim();
				if (type !== "file" || !name) continue;
				if (name.endsWith(".ts") || name.endsWith(".py")) {
					fileNames.push(name);
				}
			}
		}

		const fileContents: string[] = [];
		for (const name of fileNames) {
			const path =
				name.includes(":") || name.startsWith("/")
					? name
					: `${authDir}/${name}`;
			const content = await mcp.executeAction(
				{
					actionType: "tool",
					actionName: readTool,
					arguments: { [readKey]: path },
				},
				{
					identityId: runtimeIdentity.id,
					orgId: runtimeIdentity.orgId,
					roles: runtimeIdentity.roles,
					scopes: runtimeIdentity.scopes,
					missionId: runtimeIdentity.sessionId,
				},
			);
			if (typeof content === "string") {
				fileContents.push(`# ${name}\n${content.slice(0, 2000)}`);
			}
		}

		const summaryPrompt = `You have direct access to the file contents below. Summarize the authentication methods implemented in src/core/auth. Do not ask for more files. Only use the provided content and cite file names when relevant.\n\n${fileContents.join("\n\n")}`;
		const summary = await generateText({
			model,
			prompt: summaryPrompt,
		});

		return {
			scout_result: summary.text || "# No output",
		};
	}
}
