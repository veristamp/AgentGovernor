import { expect, test } from "bun:test";
import { z } from "zod";
import { LlmClient } from "../src/agent/llm_client";
import { OrchestratorAgent } from "../src/agent/orchestrator";
import { PolicyEngine } from "../src/policy/engine";

// Use real LLM (required for Orchestrator native looping logic to work properly)
const OPENAI_API_KEY = process.env.OPENAI_API_KEY;
if (!OPENAI_API_KEY) {
	console.warn("Skipping Orchestrator E2E test - OPENAI_API_KEY required");
	process.exit(0);
}

test("Zod Schema Sanity Check", () => {
	const schema = z.object({ query: z.string() });
	console.log("Zod Schema:", schema);
	expect(schema).toBeDefined();
	// Basic check if it behaves like a Zod schema
	expect(schema.safeParse({ query: "foo" }).success).toBe(true);
});

test("Orchestrator Agent E2E: Routing -> Scout -> Execution", async () => {
	const llmClient = new LlmClient("https://api.openai.com/v1", OPENAI_API_KEY);

	const orchestrator = new OrchestratorAgent({
		llm: llmClient,
		policy: new PolicyEngine(),
		model: "gpt-4o", // Strong model for routing
		scoutModel: "gpt-4o-mini", // Fast model for scouting
	});

	const goal =
		"Check the files in 'src/auth' directory and summarize what authentication methods are implemented.";

	console.log(`[Test] Running Orchestrator with goal: "${goal}"`);

	const result = await orchestrator.run({
		goal,
		identity: {
			roles: ["mcp:admin"], // Admin role to ensure FS access
			scopes: ["read"],
			orgId: "test-org",
		},
	});

	console.log("[Test] Orchestrator Result:\n", result.code);

	// Assertions
	expect(result).toBeDefined();
	expect(result.code).toBeDefined();

	// We expect the result to contain information about the auth methods found
	// Since 'src/auth' contains jwt.ts, oauth_demo.py, admin-client.ts, etc.
	// The summary should mention JWT, OAuth, or Admin/Agent Clients.

	const contentLower = result.code.toLowerCase(); // 'code' field might contain text summary from scout
	const hasAuthKeywords =
		contentLower.includes("jwt") ||
		contentLower.includes("oauth") ||
		contentLower.includes("admin") ||
		contentLower.includes("client");

	if (!hasAuthKeywords) {
		console.warn("Result might be missing key auth details:", result.code);
	}
	expect(hasAuthKeywords).toBe(true);
}, 120000); // 2 minute timeout
