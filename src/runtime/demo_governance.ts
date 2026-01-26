import { getMCPClientManager } from "../core/mcp/manager";
import { getMissionService } from "../core/mission/service";
import { DEFAULT_RULES, PolicyEngine } from "../core/policy/engine";
import type { RuntimeContext } from "./factory";
import type { RuntimeIdentity } from "./middleware";
import { runSubAgent } from "./sub_agent";

async function main() {
	console.log(
		"=== Governance Architecture Demo (Phase 2: Missions & Sub-Agents) ===",
	);

	// 1. Kernel Initialization
	const mcp = await getMCPClientManager();
	const policy = new PolicyEngine(DEFAULT_RULES);
	const missionService = getMissionService();

	const { createOpenAI } = await import("@ai-sdk/openai");
	const openai = createOpenAI({ apiKey: process.env.OPENAI_API_KEY });
	const rawModel = openai("gpt-4o");

	// 2. Admin Step: Create a Mission
	console.log("\n--- Admin: Creating Mission ---");
	const mission = await missionService.createMission({
		name: "Orchestration Demo",
		description: "Testing Sub-Agent Pattern",
		ownerId: "user-admin",
		orgId: "demo-org",
	});
	console.log(`Mission Created: ${mission.id}`);

	// 3. Admin Step: Create a Session
	console.log("--- Admin: Creating Session ---");
	const session = await missionService.createSession({
		missionId: mission.id,
		title: "Orchestration Session",
	});
	console.log(`Session Created: ${session.id}`);

	// 4. Construct Orchestrator Identity
	const orchestratorIdentity: RuntimeIdentity = {
		id: "agent-orchestrator",
		type: "agent",
		roles: ["mcp:admin"],
		scopes: ["*"],
		orgId: "demo-org",
		sessionId: session.id,
		missionId: mission.id,
	};

	// 5. Manual Orchestrator Loop (Simulated)
	// We don't have a "Tool Registry" for internal tools yet, so we'll just run the sub-agent directly to prove it works.
	console.log("\n--- Testing Sub-Agent Execution Directly ---");

	const toolNames = mcp.getToolNames();
	console.log(
		"Available MCP Tools:",
		toolNames.filter((t) => t.startsWith("filesystem")),
	);

	const result = await runSubAgent({
		identity: orchestratorIdentity,
		mcp,
		policy,
		model: rawModel,
		system: "You are a file explorer.",
		user: "List the files in the current directory.",
		allowedTools: ["filesystem.list_directory"], // Ensure this matches what we see in logs
	});

	console.log("\n--- Sub-Agent Result ---");
	console.log(result.final);
	console.log(`Trace Events: ${result.trace.length}`);

	await mcp.close();
}

if (import.meta.main) {
	main();
}
