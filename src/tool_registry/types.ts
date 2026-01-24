export interface ToolDescriptor {
    qualifiedName: string;
    serverPrefix: string;
    name: string;
    description: string;
    schema?: unknown;
}

export interface ToolRegistryOptions {
    dbPath?: string;
    toolsDir?: string;
}
