import { createAgentRuntime, type RuntimeContext, type RuntimeOptions } from "../runtime/factory";
import { runGovernedLoop, type GovernedLoopOptions } from "../runtime/loop";
import type { RuntimeIdentity } from "../runtime/middleware";
import {
  createChildIdentity,
  createMissionRuntime,
  type MissionRuntime,
} from "../runtime/mission";
import type {
  AgentConfig,
  AgentHandle,
  AgentSpawner,
  AgentStatus,
  SpawnOptions,
} from "./types";

export interface SpawnerOptions {
  /** Enable LLM response caching */
  enableCache?: boolean;
  /** Runtime options for cache configuration */
  runtimeOptions?: RuntimeOptions;
}

/**
 * Governed Agent Spawner
 *
 * Unified spawner for all agents. Handles:
 * - Identity propagation (child inherits mission, gets new session)
 * - Runtime creation with specific tools
 * - Governance enforcement via runGovernedLoop
 */
export class GovernedAgentSpawner implements AgentSpawner {
  private options: SpawnerOptions;

  constructor(options: SpawnerOptions = {}) {
    this.options = options;
  }

  async spawn(
    config: AgentConfig,
    parentContext: RuntimeContext,
    options: SpawnOptions = {},
  ): Promise<AgentHandle> {
    // 1. Create child identity
    const parentMission = createMissionRuntime(parentContext.identity, {
      missionId: parentContext.identity.missionId,
      sessionId: parentContext.identity.sessionId,
    });

    const childIdentity = createChildIdentity(parentMission, {
      id: `${config.id}-${Date.now()}`,
      type: "agent",
      sessionId:
        options.sessionId ||
        (options.inheritMission
          ? parentContext.identity.sessionId
          : `sess_${Date.now()}`),
    });

    // 2. Create child runtime with agent's specific tools
    const runtime = await createAgentRuntime(
      {
        ...parentContext,
        identity: childIdentity,
      },
      config.allowedTools,
      this.options.runtimeOptions,
    );

    // 3. Track execution state
    let status: AgentStatus = "idle";
    let abortController: AbortController | null = null;

    // 4. Return handle that runs the governed loop
    const handle: AgentHandle = {
      run: async (input: unknown) => {
        if (status === "running") {
          throw new Error("Agent is already running");
        }

        status = "running";
        abortController = new AbortController();

        try {
          const userPrompt =
            typeof input === "string"
              ? input
              : JSON.stringify(input, null, 2);

          const loopOptions: GovernedLoopOptions = {
            maxIterations: config.maxIterations ?? 10,
            runId: options.runId || `run-${config.id}-${Date.now()}`,
            sessionId: childIdentity.sessionId,
            runType: config.runType || "workflow",
          };

          const result = await runGovernedLoop<unknown>(
            {
              ...parentContext,
              identity: childIdentity,
            },
            runtime,
            config.systemPrompt,
            userPrompt,
            loopOptions,
          );

          status = "completed";
          return {
            final: result.final,
            iterations: result.iterations,
            trace: result.trace,
            status,
          };
        } catch (error) {
          status = "failed";
          throw error;
        }
      },

      abort: () => {
        if (abortController && status === "running") {
          abortController.abort();
          status = "aborted";
        }
      },

      getStatus: () => status,
    };

    return handle;
  }
}

/**
 * Create a default spawner instance
 */
export function createAgentSpawner(options?: SpawnerOptions): AgentSpawner {
  return new GovernedAgentSpawner(options);
}

/**
 * Convenience function to spawn and run an agent in one call
 */
export async function spawnAndRun<T = unknown>(
  config: AgentConfig,
  parentContext: RuntimeContext,
  input: unknown,
  options?: SpawnOptions,
): Promise<{
  final: T;
  iterations: number;
  trace: unknown[];
  status: AgentStatus;
}> {
  const spawner = createAgentSpawner();
  const handle = await spawner.spawn(config, parentContext, options);
  return handle.run(input) as Promise<{
    final: T;
    iterations: number;
    trace: unknown[];
    status: AgentStatus;
  }>;
}