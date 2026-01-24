export interface GcmParameter {
    type: 'string' | 'number' | 'boolean' | 'enum' | 'array' | 'object';
    description?: string;
    required?: boolean;
    default?: any;
    enum?: string[]; // For 'enum' type
    source?: 'context' | 'user' | 'inference'; // Hint for the router where to get this value
}

export interface GcmSignature {
    id: string; // e.g., "skills.data.clean"
    version: string; // e.g., "1.0.0"
    intent_embedding?: number[]; // Pre-calculated vector for high-speed routing
    description: string; // Short, functional description ( < 200 chars)
    keywords: string[]; // For BM25/Regex search if embedding is missing
    parameters: Record<string, GcmParameter>;
    compute_cost: 'low' | 'medium' | 'high';
    required_policies: string[]; // e.g. ["filesystem.write", "net.access"]
    fanout_tools: string[]; // Tools this skill orchestrates
}

export interface GcmRegistrySearchResult {
    type: 'tool_search_result';
    tool_references: {
        type: 'tool_reference';
        tool_name: string;
        signature: GcmSignature; // Include the full signature so the agent knows how to use it immediately
    }[];
}
