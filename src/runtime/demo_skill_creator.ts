import { SkillCreatorAgent } from "../agents/skill_creator/skill_creator_agent";
import type { SkillCreationRequest } from "../agents/skill_creator/types";
import { getMCPClientManager } from "../core/mcp/manager";
import { getMissionService } from "../core/mission/service";
import { DEFAULT_RULES, PolicyEngine } from "../core/policy/engine";

async function main() {
	console.log("=== Skill Creator Agent Demo (Phase 3) ===");

	// 1. Kernel Initialization
	const mcp = await getMCPClientManager();
	const policy = new PolicyEngine(DEFAULT_RULES);
	const missionService = getMissionService();

	const { createOpenAI } = await import("@ai-sdk/openai");
	const openai = createOpenAI({ apiKey: process.env.OPENAI_API_KEY });
	const llm = {
		complete: async (messages: any[], options: any) => {
			// Mock implementation if needed by legacy parts, but runSubAgent uses the model directly
			return "";
		},
	};

	// 2. Setup Mission
	console.log("\n--- Admin: Creating Mission ---");
	const mission = await missionService.createMission({
		name: "Skill Gen Mission",
		description: "Generating new skills",
		ownerId: "user-dev",
		orgId: "demo-org",
	});
	const session = await missionService.createSession({
		missionId: mission.id,
		title: "Skill Gen Session",
	});

	// 3. Prepare Request
	const request: SkillCreationRequest = {
		goal: "Create a skill that reads a JSON file from disk and returns the value of a specific key. It should take 'path' and 'key' as arguments.",
		constraints: ["Use filesystem tools", "Handle missing files gracefully"],
		requester: {
			id: "agent-skill-creator",
			roles: ["mcp:admin"], // Needs admin to write skills
			orgId: "demo-org",
			missionId: mission.id,
			sessionId: session.id,
		},
	};

	// 4. Run Skill Creator
	console.log("\n--- Running Skill Creator Agent ---");
	const agent = new SkillCreatorAgent(
		{ llm: llm as any }, // Legacy dep, mostly unused now
		{
			model: "gpt-4o",
			skillsDir: "skills_test_e2e", // Isolate test skills
			toolsPath: "tools", // Mock tools path if needed
		},
	);

	try {
		const result = await agent.run(request, { mcp }, (event) => {
			if (event.type === "question") {
				console.log(`[Question] ${event.message}`);
			} else if (event.type === "draft") {
				console.log(`[Draft] Generated draft for ${event.draft.skillId}`);
			}
		});

		console.log("\n--- Result ---");
		console.log(`Skill Created: ${result.skillRef}`);
		console.log(`Location: ${result.skillDir}`);
	} catch (e) {
		console.error("Skill Creator Failed:", e);
	}

	await mcp.close();
}

if (import.meta.main) {
	main();
}
