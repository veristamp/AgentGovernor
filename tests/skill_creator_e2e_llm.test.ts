import { expect, test } from "bun:test";
import { existsSync, rmSync } from "node:fs";
import { resolve } from "node:path";
import { LlmClient } from "../src/agents/main";
import { SkillCreatorAgent } from "../src/agents/skill_creator";
import { PolicyEngine } from "../src/core/policy/engine";

const OPENAI_API_KEY = process.env.OPENAI_API_KEY;
const OPENAI_API_BASE =
	process.env.OPENAI_API_BASE || "https://api.openai.com/v1";

const maybeTest = OPENAI_API_KEY ? test : test.skip;

maybeTest(
	"skill creator end-to-end with real LLM",
	async () => {
		const outDir = resolve("skills_test_e2e");
		const rolePerms = resolve("policy", "role_permissions_e2e.json");
		if (existsSync(outDir)) rmSync(outDir, { recursive: true, force: true });
		if (existsSync(rolePerms)) rmSync(rolePerms, { force: true });

		const policy = new PolicyEngine();
		await policy.loadRulesFromFile("policy/policy_rules.json");
		if (!OPENAI_API_KEY) {
			throw new Error("OPENAI_API_KEY is required for this test");
		}

		const agent = new SkillCreatorAgent(
			{ llm: new LlmClient(OPENAI_API_BASE, OPENAI_API_KEY), policy },
			{
				model: "gpt-4o-mini",
				toolsPath: "tools_schema.json",
				skillsDir: outDir,
				policyFilePath: "policy/policy_rules.json",
				rolePermissionsPath: rolePerms,
				maxRepairAttempts: 3,
				maxTokens: 2200,
			},
		);

		const result = await agent.run({
			goal: "Create a skill that reads a text file via filesystem tools and returns the first 20 lines as a single string.",
			constraints: [
				"Must use _bindings and filesystem tools, no open()",
				"Return a JSON object with path and preview",
			],
			requester: {
				id: "admin",
				roles: ["mcp:admin"],
				orgId: "org_e2e",
			},
		});

		expect(result.skillRef).toContain("skills:");
		expect(existsSync(resolve(result.skillDir, "signature.json"))).toBe(true);
		expect(existsSync(resolve(result.skillDir, "manifest.json"))).toBe(true);
		expect(existsSync(resolve(result.skillDir, "lib.py"))).toBe(true);
	},
	120000,
);
