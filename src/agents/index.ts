/**
 * Agents Module - Clean declarative exports
 * 
 * New pattern: AgentConfig + AgentSpawner
 */

export { runAgent, getAgentConfig, createSpawner, AgentManager } from "./manager";
export { orchestratorConfig, ORCHESTRATOR_SYSTEM_PROMPT } from "./orchestrator";
export { skillCreatorConfig, skillCreatorPhaseConfig, SKILL_CREATOR_UNIFIED_SYSTEM } from "./skill-creator";
