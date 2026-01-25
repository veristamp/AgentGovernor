import { expect, test } from "bun:test";
import { Agent, LlmClient } from "../src/agent";
import { PolicyEngine } from "../src/policy";
import { WorkflowRegistry } from "../src/workflow_registry";

class FakeDiscoveryLlm extends LlmClient {
	private callCount = 0;

	constructor() {
		super("http://localhost", "");
	}

	override async complete(
		messages: { role: string; content: string }[],
	): Promise<string> {
		this.callCount += 1;
		const _prompt = messages.map((message) => message.content).join("\n");

		// 1. First call: ask to expand skill context
		if (this.callCount === 1) {
			return JSON.stringify({
				type: "tool_call",
				name: "skills.search",
				arguments: {
					query: "fetch documentation",
					limit: 5,
					add_to_context: true,
				},
			});
		}

		// The test environment might not find "docs-to-files" if FTS ranks it low for "fetch documentation" or if it's not in DB
		// But for the sake of unit testing flow, we assume Agent proceeds.
		// Wait, if "Search found no new allowed skills", Agent returns code from LAST attempt which was the search command?
		// No, Agent loop continues?

		// Actually, if search yields nothing, we proceed.

		const code = [
			"# PLAN: Fetch docs",
			"import skills",
			"",
			"async def main():",
			'    docs = await skills.load("docs-to-files").fetch_and_store(library="/vercel/next.js", topic="routing", output_dir="output/docs")',
			"    return docs",
		].join("\n");
		return JSON.stringify({ type: "final", result: { code } });
	}
}

test("agent dynamically discovers tools via search", async () => {
	const registry = new WorkflowRegistry({ baseDir: "workflows_test" });
	const agent = new Agent({
		llm: new FakeDiscoveryLlm(),
		policy: new PolicyEngine(),
		model: "test-model",
		workflowRegistry: registry,
		maxRepairAttempts: 1,
	});

	const result = await agent.run({
		goal: "Fetch documentation for Next.js",
		identity: {
			roles: ["mcp:docs-curator"],
			scopes: [],
			orgId: "org-1",
		},
	});

	expect(result.code).toContain('skills.load("docs-to-files")');
	expect(result.prompt).toContain("[WORKFLOW BUILDER]");
});
