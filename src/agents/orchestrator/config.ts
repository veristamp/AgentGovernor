/**
 * Orchestrator Agent Configuration
 *
 * Declarative configuration for the orchestrator agent.
 */

import type { AgentConfig } from "../../executor/types";
import { ORCHESTRATOR_SYSTEM_PROMPT } from "./prompts";

export const orchestratorConfig: AgentConfig = {
	id: "orchestrator",
	name: "Orchestrator",
	description:
		"Routes requests to the best execution path (workflows, skills, or task agents)",
	systemPrompt: ORCHESTRATOR_SYSTEM_PROMPT,
	allowedTools: [
		"workflows.search",
		"skills.search",
		"skill.create",
		"task.run",
	],
	maxIterations: 10,
	runType: "workflow",
};

export default orchestratorConfig;
