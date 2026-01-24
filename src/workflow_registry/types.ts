export interface WorkflowManifest {
    skills: string[];
    tools: string[];
    io_calls?: string[];
}

export interface WorkflowMetadata {
    id: string;
    goal: string;
    createdAt: string;
    createdBy: string;
    orgId?: string;
    skills: string[];
    summary?: string;
}

export interface StoredWorkflow {
    metadata: WorkflowMetadata;
    manifest: WorkflowManifest;
    code: string;
}

export interface WorkflowSearchResult {
    metadata: WorkflowMetadata;
    score: number;
}

export interface WorkflowRegistryOptions {
    baseDir?: string;
}
