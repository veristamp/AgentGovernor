import { expect, test } from "bun:test";
import { existsSync, rmSync } from "node:fs";
import { resolve } from "node:path";
import { WorkflowRegistry } from "../src/workflow_registry";

const baseDir = resolve("workflows_gcm");

test("workflow registry saves and filters by org + skills", async () => {
	// Use unique Org ID to isolate test in shared DB environment
	const testOrgId = `org-test-${Date.now()}`;

	if (existsSync(baseDir)) {
		rmSync(baseDir, { recursive: true, force: true });
	}

	const registry = new WorkflowRegistry({ baseDir });
	const manifest = {
		skills: ["skills:docs-to-files@1"],
		tools: ["docs-to-files.fetch_and_store"],
	};

	const stored = await registry.saveWorkflow(
		"Fetch docs",
		"async def main():\n    return {}",
		manifest,
		{
			id: "user1",
			orgId: testOrgId,
		},
	);

	expect(stored.metadata.orgId).toBe(testOrgId);

	const matches = await registry.search(
		"fetch docs",
		["skills:docs-to-files@1"],
		testOrgId,
	);
	expect(matches.length).toBe(1);
	expect(matches[0]?.metadata.id).toBe(stored.metadata.id);

	const denied = await registry.search(
		"fetch docs",
		["skills:repo-insight@1"],
		testOrgId,
	);
	expect(denied.length).toBe(0);
});
