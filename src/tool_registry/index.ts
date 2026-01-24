export * from './types';
export * from './registry';

import { ToolRegistry } from './registry';

// Global singleton instance
let instance: ToolRegistry | null = null;

export function getToolRegistry(toolsDir?: string): ToolRegistry {
    if (!instance) {
        instance = new ToolRegistry({ toolsDir });
        instance.ingest();
    }
    return instance;
}
