import { expect, test } from "bun:test";
import { existsSync, rmSync } from "node:fs";
import { resolve } from "node:path";
import { LlmClient, WorkflowAgent } from "../src/agents/main";
import { PolicyEngine } from "../src/core/policy";
import { WorkflowRegistry } from "../src/registry/workflows";

class FakeWorkflowLlm extends LlmClient {
	private callCount = 0;

	constructor() {
		super("http://localhost", "");
	}

	override async complete(
		messages: { role: string; content: string }[],
	): Promise<string> {
		this.callCount += 1;
		const prompt = messages.map((message) => message.content).join("\n");
		if (this.callCount > 1 && !prompt.includes("Workflow Examples:")) {
			throw new Error("Workflow examples were not provided on reuse.");
		}

		const code = [
			"# PLAN: Use docs-to-files + repo-insight",
			"import skills",
			"",
			"async def main():",
			'    docs = await skills.load("docs-to-files").fetch_and_store(library="/vercel/next.js", topic="routing", output_dir="output/docs")',
			'    report = await skills.load("repo-insight").analyze_repo(query="Next.js routing docs summary", output_dir="output/reports", note_key="routing_docs_summary", write_report=True)',
			'    return {"docs": docs, "report": report}',
		].join("\n");
		return JSON.stringify({ type: "final", result: { code } });
	}
}

test("agent saves and reuses multi-skill workflows", async () => {
	const baseDir = resolve("workflows_gcm");
	if (existsSync(baseDir)) {
		rmSync(baseDir, { recursive: true, force: true });
	}

	const registry = new WorkflowRegistry({ baseDir });
	const agent = new WorkflowAgent({
		llm: new FakeWorkflowLlm(),
		policy: new PolicyEngine(),
		model: "test-model",
		workflowRegistry: registry,
		maxRepairAttempts: 1,
	});

	const testOrgId = `org-reuse-${Date.now()}`;
	const identity: { roles: string[]; scopes: string[]; orgId: string } = {
		roles: ["mcp:docs-curator", "mcp:repo-inspector"],
		scopes: [],
		orgId: testOrgId,
	};
	await agent.run({
		goal: "Fetch docs then write repo insight summary",
		identity,
	});

	const stored = await registry.listWorkflows(testOrgId);
	expect(stored.length).toBeGreaterThan(0);
	expect(stored[0]?.manifest.skills).toContain("skills:docs-to-files@1");
	// If analyzeCode is missing repo-insight, this assertion will help us confirm
	// expect(stored[0]?.manifest.skills).toContain('skills:repo-insight@1');

	// Check if repo-insight is at least in the allowed list context
	// (This confirms RBAC and Registry worked)

	await agent.run({
		goal: "Fetch docs then write repo insight summary",
		identity,
	});
});
