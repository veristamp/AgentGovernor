/**
 * Skill Creator Agent Configuration
 *
 * Declarative configuration for the skill creator agent.
 * Based on the implementation plan, this uses a unified (single-phase) approach
 * with capability discovery tools.
 */

import type { AgentConfig, MultiPhaseAgentConfig } from "../../executor/types";
import {
	SKILL_CREATOR_PHASE1_SYSTEM,
	SKILL_CREATOR_PHASE2_SYSTEM,
	SKILL_CREATOR_UNIFIED_SYSTEM,
} from "./prompts";

/**
 * Skill Creator - Phase-based Configuration
 *
 * Phase 1: Discovery - Find and select relevant tools
 * Phase 2: Generation - Generate skill code based on selected tools
 */
export const skillCreatorPhaseConfig: MultiPhaseAgentConfig = {
	id: "skill-creator",
	name: "Skill Creator",
	description:
		"Creates new skills by discovering tools and generating Python code",

	// Phase-based execution
	phases: [
		{
			name: "discovery",
			prompt: SKILL_CREATOR_PHASE1_SYSTEM,
			allowedTools: [
				"capability.search",
				"capability.load",
				"update_plan",
				"task.run",
			],
			maxIterations: 5,
		},
		{
			name: "generation",
			prompt: SKILL_CREATOR_PHASE2_SYSTEM,
			allowedTools: ["capability.load", "update_plan", "task.run"],
			maxIterations: 5,
		},
	],

	// Phase transition logic
	onPhaseComplete: (phase, result, context) => {
		if (phase === "discovery") {
			// Store selected tools in context for generation phase
			const selectionResult = result as { selected_tools?: string[] };
			context.selectedTools = selectionResult.selected_tools || [];
			return "generation";
		}
		return null; // Done
	},

	// Finalization (outside governed loop)
	finalize: async (result, context) => {
		// Store the skill draft in context for later finalization
		context.draft = result;
		return result;
	},

	// Required base config fields
	systemPrompt: SKILL_CREATOR_PHASE1_SYSTEM,
	allowedTools: [
		"capability.search",
		"capability.load",
		"update_plan",
		"task.run",
	],
	maxIterations: 10,
	runType: "skill",
};

/**
 * Skill Creator - Unified Configuration (Single Phase)
 *
 * Uses a single phase with iterative discovery and generation.
 * This is the recommended approach as it allows the agent to
 * dynamically discover and use tools in one continuous loop.
 */
export const skillCreatorConfig: AgentConfig = {
	id: "skill-creator",
	name: "Skill Creator",
	description:
		"Creates new skills by discovering tools and generating Python code",
	systemPrompt: SKILL_CREATOR_UNIFIED_SYSTEM,
	allowedTools: [
		"capability.search",
		"capability.load",
		"update_plan",
		"task.run",
	],
	maxIterations: 15,
	runType: "skill",
};

/**
 * Get skill creator config based on mode
 */
export function getSkillCreatorConfig(
	mode: "unified" | "phased" = "unified",
): AgentConfig | MultiPhaseAgentConfig {
	return mode === "phased" ? skillCreatorPhaseConfig : skillCreatorConfig;
}

export default skillCreatorConfig;
