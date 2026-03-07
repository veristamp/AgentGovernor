export type AgentLoopMessageRole = "system" | "user" | "assistant";

export interface AgentLoopMessage {
	role: AgentLoopMessageRole;
	content: string;
}

export type AgentLoopModelResponse =
	| {
			type: "tool_call";
			name: string;
			arguments?: Record<string, unknown>;
	  }
	| {
			type: "final";
			result: unknown;
	  };

export interface AgentLoopTool {
	name: string;
	description: string;
	inputSchema: Record<string, unknown>;
	execute(
		args: Record<string, unknown>,
		context: AgentLoopToolContext,
	): Promise<unknown>;
}

export interface AgentLoopToolContext {
	orgId?: string;
	roles?: string[];
	scopes?: string[];
	missionId?: string;
	sessionId?: string;
}

export interface AgentLoopRunOptions {
	maxIterations?: number;
	toolCallTimeoutMs?: number;
}
