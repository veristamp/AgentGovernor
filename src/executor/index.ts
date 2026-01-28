/**
 * Executor Module
 *
 * Unified execution layer for agents. Provides:
 * - AgentSpawner: Unified way to spawn agents
 * - SkillCreator: Phase-based skill creation with Engram
 * - ContextBuilder: Build runtime contexts
 * - Types: Shared types for the executor layer
 */

export * from "./types";
export * from "./agent-spawner";
export * from "./context-builder";
export * from "./skill-creator";

// Re-export for convenience
export { GovernedAgentSpawner, createAgentSpawner, spawnAndRun, type SpawnerOptions } from "./agent-spawner";
export { StandardContextBuilder, createContextBuilder, buildRuntimeContext, type RuntimeDeps } from "./context-builder";
export { runSkillCreator, type SkillCreatorInput, type DiscoveryResult, type GenerationResult } from "./skill-creator";