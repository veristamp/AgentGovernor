import { expect, test } from "bun:test";
import { existsSync, readFileSync, rmSync } from "node:fs";
import { resolve } from "node:path";
import { LlmClient } from "../src/agents/main";
import { SkillCreatorAgent } from "../src/agents/skill_creator";
import {
	closeMCPClientManager,
	getMCPClientManager,
} from "../src/core/mcp/manager";
import { PolicyEngine } from "../src/core/policy";

// Use real LLM if key is present, otherwise fallback to fake
const OPENAI_API_KEY = process.env.OPENAI_API_KEY;
const USE_REAL_LLM = !!OPENAI_API_KEY;

class FakeSkillLlm extends LlmClient {
	private callCount = 0;

	constructor() {
		super("http://localhost", "");
	}

	override async complete(
		messages: { role: string; content: string }[],
	): Promise<string> {
		this.callCount += 1;
		const prompt = messages.map((message) => message.content).join("\n");

		// Phase 1: Tool Selection
		if (this.callCount === 1) {
			if (!prompt.includes("AVAILABLE TOOLS:")) {
				throw new Error("Phase 1 prompt missing AVAILABLE TOOLS.");
			}

			return JSON.stringify({
				reasoning: "I need to fetch docs and write them to disk.",
				selected_tools: [
					"context7.query-docs",
					"context7.resolve-library-id",
					"filesystem.write-file",
					"filesystem.create-directory",
				],
				missing_capabilities: [],
				questions: [],
			});
		}

		// Phase 2: Generation
		if (this.callCount === 2) {
			if (!prompt.includes("CONTEXT (Selected Tools):")) {
				throw new Error("Phase 2 prompt missing CONTEXT (Selected Tools).");
			}

			return JSON.stringify({
				skill_id: "docs-skill",
				summary: "Fetch docs and store them locally.",
				interface: ["fetch_docs(library, topic, output_dir, file_name=None)"],
				bindings: { ctx: "context7", fs: "filesystem" },
				fanout_tools: [
					"context7.resolve-library-id",
					"context7.query-docs",
					"filesystem.create-directory",
					"filesystem.write-file",
				],
				code: "async def fetch_docs(library, topic, output_dir, file_name=None):\n    return {}",
				questions: [],
			});
		}

		return "";
	}
}

test("skill creator agent end-to-end", async () => {
	const skillDir = resolve("skills", "docs-skill");
	if (existsSync(skillDir)) {
		rmSync(skillDir, { recursive: true, force: true });
	}

	const policyPath = resolve("policy", "policy_rules.json");
	const policyBefore = readFileSync(policyPath, "utf-8");

	// Ensure we point to the real tools directory for the registry to load
	const toolsDir = resolve("tools");

	let llmClient: LlmClient;
	let modelName: string;

	if (USE_REAL_LLM) {
		console.log("Using Real OpenAI LLM for Skill Creator Test");
		if (!OPENAI_API_KEY) {
			throw new Error("OPENAI_API_KEY is required when USE_REAL_LLM=true");
		}
		llmClient = new LlmClient("https://api.openai.com/v1", OPENAI_API_KEY);
		modelName = "gpt-4o-mini";
	} else {
		console.log("Using Fake LLM for Skill Creator Test");
		llmClient = new FakeSkillLlm();
		modelName = "test-model";
	}

	const agent = new SkillCreatorAgent(
		{ llm: llmClient, policy: new PolicyEngine() },
		{
			model: modelName,
			toolsPath: toolsDir, // Points to real tools dir
			skillsDir: "skills",
			policyFilePath: policyPath,
			rolePermissionsPath: "policy/role_permissions.json",
			maxRepairAttempts: 2,
		},
	);

	const mcp = await getMCPClientManager();
	const result = await agent.run(
		{
			goal: "Fetch documentation and store it in a file",
			requester: {
				id: "admin",
				roles: ["mcp:admin", "mcp:docs-curator"],
				orgId: "org-1",
			},
		},
		{ mcp },
	);
	await closeMCPClientManager();

	console.log(`[Test] Generated Skill Ref: ${result.skillRef}`);

	expect(result.skillRef).toMatch(/^skills:.*@1$/);
	expect(result.rolesGranted).toContain("mcp:docs-curator");
	expect(result.abacProposal?.action).toBe(result.skillRef);
	expect(result.abacProposal?.conditions.allowedOrgIds).toContain("org-1");

	// Use the returned skillDir to verify files
	const manifestPath = resolve(result.skillDir, "manifest.json");
	const skillMdPath = resolve(result.skillDir, "SKILL.md");
	const libPath = resolve(result.skillDir, "lib.py");

	expect(existsSync(manifestPath)).toBe(true);
	expect(existsSync(skillMdPath)).toBe(true);
	expect(existsSync(libPath)).toBe(true);

	const manifest = JSON.parse(readFileSync(manifestPath, "utf-8")) as {
		fanoutTools?: string[];
	};

	// In real execution, exact tools might vary slightly depending on LLM choice,
	// but filesystem.write-file is essential for the goal.
	expect(manifest.fanoutTools).toBeDefined();
	// Check for either write-file or similar persistence
	expect(
		manifest.fanoutTools?.some(
			(t) => t.includes("write-file") || t.includes("write"),
		),
	).toBe(true);

	const skillMd = readFileSync(skillMdPath, "utf-8");
	expect(skillMd).toContain("## Interface");

	const policyAfter = readFileSync(policyPath, "utf-8");
	// Policy should be updated (RBAC)
	// Actually, updateRbac updates role_permissions.json, NOT policy_rules.json.
	// The test checks policy_rules.json equality, which is correct (ABAC is proposed, not written).
	expect(policyAfter).toBe(policyBefore);

	// Cleanup generated skill
	if (existsSync(result.skillDir)) {
		rmSync(result.skillDir, { recursive: true, force: true });
	}
}, 60000); // Increase timeout for real LLM calls
