/**
 * Agents Module - Clean declarative exports
 *
 * New pattern: AgentConfig + AgentSpawner
 */

export {
	AgentManager,
	createSpawner,
	getAgentConfig,
	runAgent,
} from "./manager";
export { ORCHESTRATOR_SYSTEM_PROMPT, orchestratorConfig } from "./orchestrator";
export {
	SKILL_CREATOR_UNIFIED_SYSTEM,
	skillCreatorConfig,
	skillCreatorPhaseConfig,
} from "./skill-creator";
