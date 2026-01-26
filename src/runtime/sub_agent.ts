import type { LanguageModel } from "ai";
import type { MCPClientManager } from "../core/mcp/manager";
import type { PolicyEngine } from "../core/policy/engine";
import { createAgentRuntime, type RuntimeContext } from "./factory";
import { runGovernedLoop } from "./loop";
import type { RuntimeIdentity } from "./middleware";
import type { MissionRuntime } from "./mission";
import type { TraceEvent } from "./trace";

export interface SubAgentRunOptions {
	mission: MissionRuntime;
	identity: RuntimeIdentity;
	mcp: MCPClientManager;
	policy: PolicyEngine;
	model: LanguageModel;
	system: string;
	user: string;
	allowedTools: string[];
	runId?: string;
	maxIterations?: number;
}

export async function runSubAgent<TFinal = string>(
	options: SubAgentRunOptions,
): Promise<{ final: TFinal; iterations: number; trace: TraceEvent[] }> {
	const ctx: RuntimeContext = {
		identity: options.identity,
		mcp: options.mcp,
		policy: options.policy,
		model: options.model,
	};

	const runtime = await createAgentRuntime(ctx, options.allowedTools);
	const runId = options.runId || `sub-agent-${Date.now()}`;

	return await runGovernedLoop<TFinal>(
		ctx,
		runtime,
		options.system,
		options.user,
		{
			maxIterations: options.maxIterations ?? 10,
			runId,
			sessionId: options.mission.sessionId,
		},
	);
}
