/**
 * Skill Creator Agent Module
 *
 * Declarative configuration and prompts for the skill creator agent.
 */

export * from "./config";
// Re-export for convenience
export {
	getSkillCreatorConfig,
	skillCreatorConfig,
	skillCreatorPhaseConfig,
} from "./config";
export type {
	SkillDraftResponse,
	ToolSelectionResponse,
} from "./prompts";
export * from "./prompts";
export {
	buildGenerationPrompt,
	buildRepairPrompt,
	buildSelectionPrompt,
	buildUnifiedPrompt,
	SKILL_CREATOR_PHASE1_SYSTEM,
	SKILL_CREATOR_PHASE2_SYSTEM,
	SKILL_CREATOR_UNIFIED_SYSTEM,
	SYSTEM_PROMPT_REPAIR,
} from "./prompts";
