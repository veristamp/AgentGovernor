import { readFileSync, existsSync } from 'fs';
import { resolve } from 'path';
import type { ToolDescriptor } from './types';

export interface ToolRetrieverOptions {
    toolsPath?: string;
}

function scoreText(query: string, text: string): number {
    const qTokens = query.toLowerCase().split(/\W+/).filter(Boolean);
    const hay = text.toLowerCase();
    let score = 0;
    for (const token of qTokens) {
        if (hay.includes(token)) {
            score += 1;
        }
    }
    return score;
}

export function loadTools(toolsPath?: string): ToolDescriptor[] {
    const resolved = resolve(toolsPath ?? 'tools_schema.json');
    if (!existsSync(resolved)) {
        return [];
    }
    const raw = readFileSync(resolved, 'utf-8');
    const data = JSON.parse(raw) as Array<{
        qualified_name?: string;
        qualifiedName?: string;
        server_prefix?: string;
        serverPrefix?: string;
        name?: string;
        description?: string;
        schema?: unknown;
    }>;
    const descriptors = data
        .map((tool): ToolDescriptor | null => {
            const qualifiedName = String(tool.qualified_name ?? tool.qualifiedName ?? '').trim();
            const serverPrefix = String(tool.server_prefix ?? tool.serverPrefix ?? '').trim();
            const name = String(tool.name ?? '').trim();
            if (!qualifiedName || !serverPrefix || !name) {
                return null;
            }
            return {
                qualifiedName,
                serverPrefix,
                name,
                description: tool.description ?? '',
                ...(tool.schema !== undefined ? { schema: tool.schema } : {}),
            };
        })
        .filter((entry): entry is ToolDescriptor => entry !== null);

    return descriptors;
}

export function retrieveRelevantTools(
    goal: string,
    constraints: string[],
    options: ToolRetrieverOptions = {},
    limit: number = 8
): ToolDescriptor[] {
    const tools = loadTools(options.toolsPath);
    const searchText = [goal, ...constraints].join(' ').trim();
    const scored = tools
        .map((tool) => {
            const text = `${tool.qualifiedName} ${tool.description}`;
            return { tool, score: scoreText(searchText, text) };
        })
        .filter((entry) => entry.score > 0)
        .sort((a, b) => b.score - a.score || a.tool.qualifiedName.localeCompare(b.tool.qualifiedName));

    return scored.slice(0, limit).map((entry) => entry.tool);
}

export function expandTools(
    existing: ToolDescriptor[],
    goal: string,
    constraints: string[],
    options: ToolRetrieverOptions = {},
    limit: number = 12
): ToolDescriptor[] {
    const existingSet = new Set(existing.map((tool) => tool.qualifiedName));
    const candidates = retrieveRelevantTools(goal, constraints, options, limit * 3);
    const merged = [...existing];
    for (const tool of candidates) {
        if (!existingSet.has(tool.qualifiedName)) {
            merged.push(tool);
            existingSet.add(tool.qualifiedName);
            if (merged.length >= limit) break;
        }
    }
    return merged;
}
