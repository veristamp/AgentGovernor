import { getMCPClientManager } from "../core/mcp/manager";
import { getMissionService } from "../core/mission/service";
import { DEFAULT_RULES, PolicyEngine } from "../core/policy/engine";
import { EngramServiceImpl } from "../core/engram/service";
import { SkillRegistry } from "../registry/skills/registry";
import { ToolRegistry } from "../registry/tools/registry";
import { WorkflowRegistry } from "../registry/workflows";
import { runRecursiveAgent } from "../agents/recursive/agent";
import type { RuntimeIdentity } from "../runtime/middleware";

async function main() {
    console.log("=== MyKBOS: Recursive Agent + Engram (Graph-Native) ===");

    // 1. Kernel Layer
    const mcp = await getMCPClientManager();
    const policy = new PolicyEngine(DEFAULT_RULES);
    const missionService = getMissionService();

    // 2. Engram Layer (Memory)
    const engram = new EngramServiceImpl();
    const toolRegistry = new ToolRegistry(); // Required for loader

    // 3. Runtime Layer (Mission)
    console.log("\n--- Spawning Mission ---");
    const mission = await missionService.createMission({
        name: "MyKBOS System Boot",
        description: "Testing RLM+Engram Integration",
        ownerId: "root",
        orgId: "system"
    });
    const session = await missionService.createSession({
        missionId: mission.id,
        title: "User Shell"
    });

    const identity: RuntimeIdentity = {
        id: "rlm-agent-01",
        type: "agent",
        roles: ["mcp:admin"], // Full access for testing
        scopes: ["*"],
        orgId: "system",
        missionId: mission.id,
        sessionId: session.id
    };

    const { createOpenAI } = await import("@ai-sdk/openai");
    const openai = createOpenAI({ apiKey: process.env.OPENAI_API_KEY });
    const model = openai("gpt-4o");

    // 4. Execution Layer (RLM)
    const goal = "I need to parse a JSON file. What tools or skills do I have for this?";
    console.log(`\n--- RLM Execution: "${goal}" ---`);

    try {
        const result = await runRecursiveAgent(goal, {
            identity,
            mcp,
            policy,
            model,
            engram,
            toolRegistry
        });

        console.log("\n--- Final Output ---");
        console.log(result.final);
        console.log(`Trace Events: ${result.trace.length}`);
    } catch (e) {
        console.error("Agent Crashed:", e);
    }

    await mcp.close();
}

if (import.meta.main) {
    main();
}
