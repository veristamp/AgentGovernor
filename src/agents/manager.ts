import type { PolicyEngine } from "../core/policy/engine";
import type { MCPClientManager } from "../core/mcp/manager";
import type { LlmClient } from "./main/llm_client";
import type { AgentOptions } from "./main/agent";
import { WorkflowAgent } from "./main/agent";
import { OrchestratorAgent } from "./main/orchestrator";
import type {
  SkillCreatorDependencies,
  SkillCreatorOptions,
} from "./skill_creator/types";
import { SkillCreatorAgent } from "./skill_creator/skill_creator_agent";
import type { RecursiveAgentConfig } from "./recursive/agent";
import { runRecursiveAgent } from "./recursive/agent";

export type AgentId =
  | "orchestrator"
  | "workflow"
  | "skill_creator"
  | "recursive";

export const DEFAULT_AGENT_ID: AgentId = "orchestrator";

export type AgentConfigMap = {
  orchestrator: {
    llm: LlmClient;
    policy: PolicyEngine;
    model: string;
    scoutModel?: string;
  };
  workflow: AgentOptions;
  skill_creator: {
    deps: SkillCreatorDependencies;
    options: SkillCreatorOptions;
  };
  recursive: RecursiveAgentConfig;
};

export type AgentInstanceMap = {
  orchestrator: OrchestratorAgent;
  workflow: WorkflowAgent;
  skill_creator: SkillCreatorAgent;
  recursive: { run: (goal: string) => ReturnType<typeof runRecursiveAgent> };
};

export class AgentManager {
  readonly defaultId: AgentId;

  constructor(defaultId: AgentId = DEFAULT_AGENT_ID) {
    this.defaultId = defaultId;
  }

  list(): AgentId[] {
    return ["orchestrator", "workflow", "skill_creator", "recursive"];
  }

  create<T extends AgentId>(
    id: T,
    config: AgentConfigMap[T],
  ): AgentInstanceMap[T] {
    if (id === "orchestrator") {
      return new OrchestratorAgent(
        config as AgentConfigMap["orchestrator"],
      ) as AgentInstanceMap[T];
    }
    if (id === "workflow") {
      return new WorkflowAgent(config as AgentOptions) as AgentInstanceMap[T];
    }
    if (id === "skill_creator") {
      const cfg = config as AgentConfigMap["skill_creator"];
      return new SkillCreatorAgent(
        cfg.deps,
        cfg.options,
      ) as AgentInstanceMap[T];
    }
    const recursiveConfig = config as AgentConfigMap["recursive"];
    return {
      run: (goal: string) => runRecursiveAgent(goal, recursiveConfig),
    } as AgentInstanceMap[T];
  }
}
