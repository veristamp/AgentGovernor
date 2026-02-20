import type { LanguageModel } from "ai";
import type { RuntimeContext } from "../runtime/factory";
import type { RuntimeIdentity } from "../runtime/middleware";
import type { TraceEvent } from "../runtime/trace";

/**
 * Agent Configuration - Declarative definition of an agent
 */
export interface AgentConfig {
	id: string;
	name: string;
	description: string;
	systemPrompt: string;
	allowedTools: string[];
	maxIterations?: number;
	runType?: "workflow" | "skill" | "tool" | "research";
}

/**
 * Agent Phase Configuration for multi-phase agents (e.g., skill-creator)
 */
export interface AgentPhaseConfig {
	name: string;
	prompt: string;
	allowedTools: string[];
	maxIterations?: number;
}

/**
 * Multi-phase Agent Configuration
 */
export interface MultiPhaseAgentConfig extends AgentConfig {
	phases: AgentPhaseConfig[];
	onPhaseComplete?: (
		phase: string,
		result: unknown,
		context: Record<string, unknown>,
	) => string | null | Promise<string | null>;
	finalize?: (
		result: unknown,
		context: Record<string, unknown>,
	) => Promise<unknown>;
}

/**
 * Agent Handle - Interface to control and interact with a spawned agent
 */
export interface AgentHandle<T = AgentExecutionResult> {
	run: (input: unknown) => Promise<T>;
	abort: () => void;
	getStatus: () => AgentStatus;
}

/**
 * Agent Status
 */
export type AgentStatus =
	| "idle"
	| "running"
	| "completed"
	| "failed"
	| "aborted";

/**
 * Agent Spawner Interface
 */
export interface AgentSpawner {
	spawn: (
		config: AgentConfig,
		parentContext: RuntimeContext,
		options?: SpawnOptions,
	) => Promise<AgentHandle>;
}

/**
 * Options for spawning an agent
 */
export interface SpawnOptions {
	runId?: string;
	sessionId?: string;
	inheritMission?: boolean;
}

/**
 * Agent Execution Result
 */
export interface AgentExecutionResult<T = unknown> {
	final: T;
	iterations: number;
	trace: TraceEvent[];
	status: AgentStatus;
}

/**
 * Runtime Dependencies for Agent Spawning
 */
export interface RuntimeDeps {
	identity: RuntimeIdentity;
	mcp: RuntimeContext["mcp"];
	policy: RuntimeContext["policy"];
	model: LanguageModel;
}

/**
 * Shared Registry Context
 * Single source of truth for all registries
 */
export interface SharedRegistryContext {
	getToolNames: () => string[];
	getCapabilityRegistry: () => unknown;
}

/**
 * Factory for creating AgentRuntime instances
 */
export interface RuntimeFactory {
	create: (
		identity: RuntimeIdentity,
		allowedTools: string[],
	) => Promise<{
		model: LanguageModel;
		tools: Array<{
			name: string;
			description: string;
			inputSchema: Record<string, unknown>;
			execute: (args: Record<string, unknown>) => Promise<unknown>;
		}>;
	}>;
}
