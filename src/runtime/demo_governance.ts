import { getMCPClientManager } from "../mcp-client/manager";
import { DEFAULT_RULES, PolicyEngine } from "../policy/engine";
import { createAgentRuntime, type RuntimeContext } from "./factory";
import { runGovernedLoop } from "./loop";
import type { RuntimeIdentity } from "./middleware";

// Mock Identity
const identity: RuntimeIdentity = {
	id: "demo-agent",
	type: "agent",
	roles: ["mcp:demo"],
	scopes: ["*"], // Allow everything for demo
	orgId: "demo-org",
	sessionId: "sess_demo_1", // Triggers Caching & Tracing
};

async function main() {
	console.log("=== Governance Architecture Demo ===");

	// 1. Kernel Initialization
	const mcp = await getMCPClientManager();
	const policy = new PolicyEngine(DEFAULT_RULES);

	const { createOpenAI } = await import("@ai-sdk/openai");
	const openai = createOpenAI({ apiKey: process.env.OPENAI_API_KEY });
	const rawModel = openai("gpt-4o");

	const ctx: RuntimeContext = {
		identity,
		mcp,
		policy,
		model: rawModel,
	};

	// 2. Factory: Create the User Space Runtime
	console.log("Creating Agent Runtime...");
	// Requesting tools that match Skill Creator needs (e.g. filesystem for build, maybe a registry tool)
	const runtime = await createAgentRuntime(ctx, ["filesystem.list_files"]);

	console.log(`Governed Model: ${(runtime.model as any).modelId}`);
	console.log(
		`Available Tools: ${runtime.tools.map((t) => t.name).join(", ")}`,
	);

	// 3. Execution (The Loop)
	console.log("\n--- Starting Loop ---");

	try {
		const result = await runGovernedLoop(
			ctx,
			runtime,
			"You are a helpful assistant. Use tools if needed.",
			"List files in current directory.",
			{ maxIterations: 5 },
		);

		console.log("\n--- Loop Result ---");
		console.log(result.final);
		console.log(`Trace Events: ${result.trace.length}`);
	} catch (e) {
		console.error("Loop Failed:", e);
	}

	await mcp.close();
}

if (import.meta.main) {
	main();
}
