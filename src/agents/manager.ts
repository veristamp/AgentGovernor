import type { LanguageModel } from "ai";
import type { MCPClientManager } from "../core/mcp/manager";
import type { PolicyEngine } from "../core/policy/engine";
import { type AgentConfig, createAgentSpawner, spawnAndRun } from "../executor";
import { buildRuntimeContext } from "../executor/context-builder";
import type { RuntimeIdentity } from "../runtime/middleware";
import { orchestratorConfig } from "./orchestrator";
import { skillCreatorConfig } from "./skill-creator";

export type AgentId = "orchestrator" | "skill-creator" | "task";

interface AgentDeps {
	identity: RuntimeIdentity;
	mcp: MCPClientManager;
	policy: PolicyEngine;
	model: LanguageModel;
}

/** Get declarative config for any agent */
export function getAgentConfig(id: AgentId): AgentConfig {
	switch (id) {
		case "orchestrator":
			return orchestratorConfig;
		case "skill-creator":
			return skillCreatorConfig;
		case "task":
			return {
				id: "task",
				name: "Task Agent",
				description: "Focused sub-task executor",
				systemPrompt:
					"You are a focused task agent. Solve the specific task and return a concise result.",
				allowedTools: [],
				maxIterations: 8,
				runType: "tool",
			};
		default:
			throw new Error(`Unknown agent: ${id}`);
	}
}

/** Run an agent by ID with the new spawner - streamlined */
export async function runAgent<T = unknown>(
	id: AgentId,
	deps: AgentDeps,
	input: unknown,
	options?: { runId?: string; maxIterations?: number },
): Promise<{ final: T; iterations: number; trace: unknown[] }> {
	const config = getAgentConfig(id);
	if (options?.maxIterations) config.maxIterations = options.maxIterations;

	const ctx = buildRuntimeContext(deps);
	return spawnAndRun(config, ctx, input, {
		runId: options?.runId || `${id}-${Date.now()}`,
		inheritMission: true,
	});
}

/** Agent Manager - Clean declarative interface */
export class AgentManager {
	list(): AgentId[] {
		return ["orchestrator", "skill-creator", "task"];
	}

	async run<T = unknown>(
		id: AgentId,
		deps: AgentDeps,
		input: unknown,
		options?: { runId?: string; maxIterations?: number },
	): Promise<{ final: T; iterations: number; trace: unknown[] }> {
		return runAgent(id, deps, input, options);
	}
}

/** Convenience: Create spawner with deps */
export function createSpawner(deps: AgentDeps) {
	return {
		spawn: (config: AgentConfig, options?: { runId?: string }) => {
			const ctx = buildRuntimeContext(deps);
			const spawner = createAgentSpawner();
			return spawner.spawn(config, ctx, { ...options, inheritMission: true });
		},
		runAgent: (
			id: AgentId,
			input: unknown,
			options?: { runId?: string; maxIterations?: number },
		) => runAgent(id, deps, input, options),
	};
}
