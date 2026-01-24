import { getToolRegistry } from '../tool_registry';
import type { ToolDescriptor } from '../tool_registry';

export interface ToolRetrieverOptions {
    toolsPath?: string; // Kept for interface compatibility
}

/**
 * Retrieves relevant tools using SQLite FTS.
 */
export function retrieveRelevantTools(
    goal: string,
    constraints: string[],
    options: ToolRetrieverOptions = {},
    limit: number = 10
): ToolDescriptor[] {
    const reg = getToolRegistry(options.toolsPath ? 'tools' : undefined);
    
    const query = [goal, ...constraints].join(' ');
    return reg.search(query, limit);
}

/**
 * Loads all tools.
 */
export function loadTools(toolsPath?: string): ToolDescriptor[] {
    const reg = getToolRegistry(toolsPath ? 'tools' : undefined);
    return reg.getAll();
}

/**
 * Expands a set of tools by searching for more based on the goal.
 */
export function expandTools(
    existing: ToolDescriptor[],
    goal: string,
    constraints: string[],
    options: ToolRetrieverOptions = {},
    limit: number = 15
): ToolDescriptor[] {
    const reg = getToolRegistry(options.toolsPath ? 'tools' : undefined);
    const existingIds = new Set(existing.map(t => t.qualifiedName));
    
    const query = [goal, ...constraints].join(' ');
    const candidates = reg.search(query, limit * 2);
    
    const result = [...existing];
    
    for (const tool of candidates) {
        if (!existingIds.has(tool.qualifiedName)) {
            result.push(tool);
            existingIds.add(tool.qualifiedName);
            if (result.length >= limit) break;
        }
    }
    
    return result;
}
