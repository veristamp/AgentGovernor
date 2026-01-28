/**
 * Skill Creator Agent Module
 *
 * Declarative configuration and prompts for the skill creator agent.
 */

export * from "./config";
export * from "./prompts";

// Re-export for convenience
export {
  skillCreatorConfig,
  skillCreatorPhaseConfig,
  getSkillCreatorConfig,
} from "./config";
export {
  buildSelectionPrompt,
  buildGenerationPrompt,
  buildRepairPrompt,
  buildUnifiedPrompt,
  SKILL_CREATOR_PHASE1_SYSTEM,
  SKILL_CREATOR_PHASE2_SYSTEM,
  SKILL_CREATOR_UNIFIED_SYSTEM,
  SYSTEM_PROMPT_REPAIR,
} from "./prompts";
export type {
  ToolSelectionResponse,
  SkillDraftResponse,
} from "./prompts";