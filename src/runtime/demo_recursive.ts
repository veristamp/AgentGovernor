import { getMCPClientManager } from "../core/mcp/manager";
import { getMissionService } from "../core/mission/service";
import { DEFAULT_RULES, PolicyEngine } from "../core/policy/engine";
import { createCapabilitySearchTool } from "../core/capabilities/discovery";
import { getEngramService } from "../core/engram/service";
import { createAgentRuntime, type RuntimeContext } from "./factory";
import { runGovernedLoop } from "./loop";
import type { RuntimeIdentity } from "./middleware";

async function main() {
  console.log("=== Recursive Discovery Demo (The Grand Fusion) ===");

  // 1. Kernel Initialization
  const mcp = await getMCPClientManager();
  const policy = new PolicyEngine(DEFAULT_RULES);
  const missionService = getMissionService();

  // 2. Initialize Engram (The Memory)
  const engram = getEngramService();

  const { createOpenAI } = await import("@ai-sdk/openai");
  const openai = createOpenAI({ apiKey: process.env.OPENAI_API_KEY });
  const model = openai("gpt-4o");

  // 3. Setup Mission
  console.log("\n--- Admin: Creating Mission ---");
  const mission = await missionService.createMission({
    name: "Recursive Discovery Mission",
    description: "Agent dynamically finds tools to solve problems",
    ownerId: "user-admin",
    orgId: "demo-org",
  });
  const session = await missionService.createSession({
    missionId: mission.id,
    title: "Discovery Session",
  });

  // 4. Construct Identity
  const identity: RuntimeIdentity = {
    id: "agent-recursive-1",
    type: "agent",
    roles: ["mcp:admin"],
    scopes: ["*"],
    orgId: "demo-org",
    missionId: mission.id,
    sessionId: session.id,
  };

  // 5. Create Runtime with ONLY the Discovery Tool
  // This is the "DIY Agent" - it starts with almost nothing.
  const ctx: RuntimeContext = {
    identity,
    mcp,
    policy,
    model,
  };

  // Create the "Universal Discovery Tool"
  const discoveryTool = createCapabilitySearchTool({ engram });

  const runtime = await createAgentRuntime(ctx, []); // Start empty
  runtime.tools.push(discoveryTool); // Inject discovery

  // 6. Run the Loop
  console.log("\n--- Starting Recursive Agent ---");
  const systemPrompt = `You are a Recursive Agent. You solve tasks by finding and using capabilities.
    
    You have ONE core tool: 'capability_search'.
    1. Analyze the user's request.
    2. Use 'capability_search' to find Tools, Skills, or Workflows that match the request.
    3. If you find a Skill or Tool you need, ASK the user (simulated) or just explain that you WOULD use it if you could load it dynamically (in this demo, we just find it).
    
    In a full RLM implementation, you would dynamically load the discovered tool/skill into your context. For now, prove you can find the right "lego block" for the job.`;

  const userPrompt =
    "I need to read a JSON file and get a specific key from it. Do we have anything for that?";

  try {
    const result = await runGovernedLoop(
      ctx,
      runtime,
      systemPrompt,
      userPrompt,
      { maxIterations: 5 },
    );

    console.log("\n--- Result ---");
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
