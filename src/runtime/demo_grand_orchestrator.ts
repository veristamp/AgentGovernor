import { OrchestratorAgent } from "../agents/main/orchestrator";
import type { AgentRequest } from "../agents/main/types";
import { getMCPClientManager } from "../core/mcp/manager";
import { getMissionService } from "../core/mission/service";
import { DEFAULT_RULES, PolicyEngine } from "../core/policy/engine";

async function main() {
	console.log("=== Grand Orchestrator Demo (Phase 4) ===");

	// 1. Kernel Initialization
	const mcp = await getMCPClientManager();
	const policy = new PolicyEngine(DEFAULT_RULES);
	const missionService = getMissionService();

	const { createOpenAI } = await import("@ai-sdk/openai");
	const openai = createOpenAI({ apiKey: process.env.OPENAI_API_KEY });
	const llm = {
		complete: async () => "", // Mock
	};

	// 2. Setup Mission
	console.log("\n--- Admin: Creating Mission ---");
	const mission = await missionService.createMission({
		name: "Autonomous Generation Mission",
		description: "Orchestrator creating skills on demand",
		ownerId: "user-admin",
		orgId: "demo-org",
	});
	const session = await missionService.createSession({
		missionId: mission.id,
		title: "Orchestrator Session",
	});

	// 3. Prepare Request
	const request: AgentRequest = {
		goal: "I need a way to count the number of lines in a Python file. Create a skill for this if one doesn't exist.",
		identity: {
			id: "agent-orchestrator",
			roles: ["mcp:admin"], // Needs admin to write skills
			scopes: ["*"],
			orgId: "demo-org",
			missionId: mission.id,
			sessionId: session.id,
		},
	};

	// 4. Run Orchestrator
	console.log("\n--- Running Orchestrator ---");
	const orchestrator = new OrchestratorAgent({
		llm: llm as any,
		policy,
		model: "gpt-4o",
	});

	try {
		const result = await orchestrator.run(request);

		console.log("\n--- Orchestrator Result ---");
		console.log(result.code);
		console.log("Plan:", result.plan);
	} catch (e) {
		console.error("Orchestrator Failed:", e);
	}

	await mcp.close();
}

if (import.meta.main) {
	main();
}
