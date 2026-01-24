export interface RegistryItem {
	id: string;
	type: "tool" | "skill" | "workflow";
	name: string;
	description: string;
	metadata: Record<string, unknown>; // JSON stored as string
	embedding?: number[]; // Future proofing
	searchText: string; // For FTS
}

export interface ToolItem extends RegistryItem {
	type: "tool";
	serverPrefix: string;
	schema: Record<string, unknown>;
}

export interface SkillItem extends RegistryItem {
	type: "skill";
	skillRef: string;
	version: string;
	interfaces: string[];
	bindings: Record<string, string>;
	fanoutTools: string[];
}

export interface WorkflowItem extends RegistryItem {
	type: "workflow";
	orgId: string;
	goal: string;
	code: string;
	skills: string[];
}
