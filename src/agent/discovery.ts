import { ToolRegistry } from '../tool_registry/registry';
import type { ToolDescriptor } from '../tool_registry/types';
import type { AgentIdentityScope } from './types';
import { getRolePermissionsAsync, matchesPermission } from '../policy/roles';

export interface SearchToolResult {
    tool_references: Array<{
        type: 'tool_reference';
        tool_name: string;
    }>;
}

export class RegistrySearchTool {
    private toolRegistry: ToolRegistry;

    constructor() {
        this.toolRegistry = new ToolRegistry();
    }

    public getDefinition() {
        return {
            name: 'tool_search_tool_bm25',
            description: 'Search for relevant tools using natural language queries. Use this when you need tools that are not currently in your context.',
            input_schema: {
                type: 'object',
                properties: {
                    query: {
                        type: 'string',
                        description: 'Natural language query describing the capabilities you need (e.g. "search documentation", "edit files")'
                    }
                },
                required: ['query']
            }
        };
    }

    public async execute(query: string, identity: AgentIdentityScope): Promise<SearchToolResult> {
        const results = await this.toolRegistry.search(query, 10); // Search broad
        
        // Filter results based on RBAC permissions
        const allowedResults = [];
        for (const tool of results) {
            if (await this.isToolAllowed(tool.qualifiedName, identity)) {
                allowedResults.push(tool);
            }
        }
        
        return {
            tool_references: allowedResults.slice(0, 5).map((t: ToolDescriptor) => ({
                type: 'tool_reference',
                tool_name: t.qualifiedName
            }))
        };
    }

    private async isToolAllowed(toolName: string, identity: AgentIdentityScope): Promise<boolean> {
        // Admin bypass
        if (identity.roles?.includes('mcp:admin')) return true;

        const permissions = await getRolePermissionsAsync(identity.roles ?? []);
        
        // Check for wildcard or explicit match
        if (matchesPermission(permissions, '*')) return true;
        if (matchesPermission(permissions, toolName)) return true;

        // If no explicit permission, deny
        // This enforces strict RBAC for tools
        return false;
    }
}
