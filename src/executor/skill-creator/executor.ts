/**
 * Skill Creator Executor
 *
 * Phase-based execution for skill creation:
 * 1. Discovery Phase: Find relevant tools using Engram
 * 2. Generation Phase: Generate skill code based on selected tools
 */

import type { RuntimeContext } from "../../runtime/factory";
import { createAgentSpawner, type AgentConfig } from "../";
import { skillCreatorConfig, buildSelectionPrompt, buildGenerationPrompt } from "../../agents/skill-creator";
import { getEngramService } from "../../core/engram";
import type { EngramLookupResult } from "../../core/engram/types";

export interface SkillCreatorInput {
  goal: string;
  constraints?: string[];
  requester: {
    id: string;
    roles: string[];
    orgId?: string;
    teamId?: string;
  };
}

export interface DiscoveryResult {
  selected_tools: string[];
  execution_graph?: unknown;
  reasoning: string;
  missing_capabilities?: string[];
}

export interface GenerationResult {
  skill_id: string;
  summary: string;
  interface: string[];
  bindings: Record<string, string>;
  fanout_tools: string[];
  code: string;
  examples: Array<{ title?: string; description?: string; code: string }>;
}

/** Run skill creation with Engram-enhanced discovery */
export async function runSkillCreator(
  ctx: RuntimeContext,
  input: SkillCreatorInput,
  options?: { runId?: string; enablePhases?: boolean }
): Promise<{ final: GenerationResult; iterations: number; trace: unknown[] }> {
  const engram = getEngramService();
  const spawner = createAgentSpawner();

  // Phase 1: Discovery with Engram
  const discoveryConfig: AgentConfig = {
    id: "skill-creator-discovery",
    name: "Skill Creator - Discovery",
    description: "Discover relevant tools for skill creation",
    systemPrompt: `You are the Skill Creator (Discovery Phase).
Your goal: Find the best tools to build a skill.

Rules:
1. Use engram_search to find relevant tools
2. Use capability_load to inspect tool schemas
3. Select minimal tool set needed
4. Output JSON: { selected_tools: string[], reasoning: string, execution_graph?: object }`,
    allowedTools: ["capability_search", "capability_discover", "system.load_capability"],
    maxIterations: 5,
    runType: "skill",
  };

  // Enhance discovery with Engram pre-search
  const engramResults = await engram.search(input.goal, 10);
  const toolCandidates = engramResults.nodes
    .filter(n => n.type === "tool")
    .map(n => ({ qualifiedName: n.id, description: n.description }));

  const discoveryHandle = await spawner.spawn(
    discoveryConfig,
    ctx,
    { runId: `${options?.runId || Date.now()}-discovery`, inheritMission: true }
  );

  const discoveryPrompt = buildSelectionPrompt(
    input.goal,
    toolCandidates,
    input.constraints || []
  );

  const discoveryResult = await discoveryHandle.run({
    goal: input.goal,
    constraints: input.constraints,
    available_tools: toolCandidates,
  });

  const discovery = discoveryResult.final as DiscoveryResult;

  // Phase 2: Generation
  const generationConfig: AgentConfig = {
    id: "skill-creator-generation",
    name: "Skill Creator - Generation",
    description: "Generate skill code from selected tools",
    systemPrompt: `You are the Skill Creator (Generation Phase).
Create Python skill code using ONLY the selected tools.

Rules:
1. Use asyncio.gather for parallel tool calls
2. All external effects through tools only
3. No direct file/network/process APIs
4. Output JSON: { skill_id, summary, interface, bindings, fanout_tools, code, examples }`,
    allowedTools: ["system.load_capability"],
    maxIterations: 5,
    runType: "skill",
  };

  // Load full tool schemas for selected tools
  const selectedToolDetails = await Promise.all(
    discovery.selected_tools.map(async (toolName) => {
      const node = await engram.inspect(toolName);
      return {
        qualifiedName: toolName,
        description: node?.description || "",
        schema: node?.structure?.inputs || {},
      };
    })
  );

  const generationHandle = await spawner.spawn(
    generationConfig,
    ctx,
    { runId: `${options?.runId || Date.now()}-generation`, inheritMission: true }
  );

  const { system, user } = buildGenerationPrompt(
    input.goal,
    selectedToolDetails,
    discovery.reasoning
  );

  const generationResult = await generationHandle.run({ system, user });
  const final = generationResult.final as GenerationResult;

  return {
    final,
    iterations: (discoveryResult as any).iterations + (generationResult as any).iterations,
    trace: [...((discoveryResult as any).trace || []), ...((generationResult as any).trace || [])],
  };
}