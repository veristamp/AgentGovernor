export interface SkillParameter {
	name: string;
	type: "string" | "number" | "boolean" | "enum" | "array" | "object" | "any";
	description?: string;
	required?: boolean;
	default?: unknown;
	enum?: string[];
	source?: "context" | "user" | "inference";
}

export interface SkillReturn {
	type: "string" | "number" | "boolean" | "enum" | "array" | "object" | "any";
	description?: string;
}

export interface SkillFunctionSignature {
	name: string;
	summary?: string;
	params: SkillParameter[];
	returns?: SkillReturn;
}

export interface SkillExample {
	title?: string;
	description?: string;
	code: string;
}

export interface GcmSignature {
	skillRef: string; // e.g., "skills:docs-to-files@1"
	skillId: string; // e.g., "docs-to-files"
	version: string; // e.g., "1"
	description: string;
	keywords: string[];
	functions: SkillFunctionSignature[];
	examples: SkillExample[];
	dependencies?: string[];
	requiredPolicies?: string[];
	fanoutTools?: string[];
}

export interface GcmRegistrySearchResult {
	type: "tool_search_result";
	tool_references: {
		type: "tool_reference";
		tool_name: string;
		signature: GcmSignature; // Include the full signature so the agent knows how to use it immediately
	}[];
}
