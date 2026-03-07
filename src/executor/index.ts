/**
 * Executor Module
 *
 * Unified execution layer for agents. Provides:
 * - AgentSpawner: Unified way to spawn agents
 * - SkillCreator: Phase-based skill creation with Engram
 * - ContextBuilder: Build runtime contexts
 * - Types: Shared types for the executor layer
 */

export * from "./agent-spawner";
// Re-export for convenience
export {
	createAgentSpawner,
	GovernedAgentSpawner,
	type SpawnerOptions,
	spawnAndRun,
} from "./agent-spawner";
export * from "./context-builder";
export {
	buildRuntimeContext,
	createContextBuilder,
	type RuntimeDeps,
	StandardContextBuilder,
} from "./context-builder";
export * from "./skill-creator";
export {
	type DiscoveryResult,
	type GenerationResult,
	runSkillCreator,
	type SkillCreatorInput,
} from "./skill-creator";
export * from "./types";
