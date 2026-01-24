#!/usr/bin/env bun
/**
 * Tool Schema Dumper - Creates structured tools/ directory.
 *
 * This is LAYER 1 of the architecture:
 *   tools/           <- Raw MCP tool definitions (this script creates)
 *   skills/          <- Composed tasks using tools (created separately)
 *   workflows/       <- Business logic using skills (created by agent)
 *
 * Output structure:
 *   tools/
 *     <server>/
 *       <tool-name>.md    <- Human-readable description
 *       <tool-name>.json  <- API schema for programmatic use
 *     ...
 *
 * Usage:
 *   bun run src/list-tools.ts
 *
 * This should be run whenever mcp_servers.json changes.
 */

import { mkdir, rm, writeFile } from 'node:fs/promises';
import path from 'node:path';

import { MCPClientManager } from './mcp-client/index.js';
import type { ToolInfo } from './mcp-client/types.js';

const TOOLS_DIR = path.resolve('tools');

// Type definitions
interface ToolData {
  qualifiedName: string;
  serverPrefix: string;
  name: string;
  originalName: string;
  description: string;
  schema: Record<string, unknown>;
}

interface PropertyDef {
  type?: string;
  description?: string;
  default?: unknown;
}

// Normalize a tool name: replace underscores with hyphens, lowercase
const normalizeName = (name: string): string => name.replace(/_/g, '-').toLowerCase();

// Type mapping for Python signature generation
const TYPE_MAP: Record<string, string> = {
  string: 'str',
  integer: 'int',
  number: 'float',
  boolean: 'bool',
  array: 'list',
  object: 'dict',
};

const formatSignature = (name: string, schema: Record<string, unknown>): string => {
  const props = (schema.properties ?? {}) as Record<string, PropertyDef>;
  const required = new Set((schema.required ?? []) as string[]);

  const args: string[] = [];
  for (const [paramName, paramDef] of Object.entries(props)) {
    const pyType = TYPE_MAP[paramDef.type ?? 'any'] ?? 'any';
    if (required.has(paramName)) {
      args.push(`${paramName}: ${pyType}`);
    } else {
      const def = paramDef.default;
      if (def !== undefined) {
        const defStr = typeof def === 'string' ? `"${def}"` : String(def);
        args.push(`${paramName}: ${pyType} = ${defStr}`);
      } else {
        args.push(`${paramName}: ${pyType} = None`);
      }
    }
  }

  return `${name}(${args.join(', ')})`;
};

const generateToolMd = (tool: ToolData): string => {
  const { name, qualifiedName, description, schema } = tool;
  const sig = formatSignature(name, schema);

  const props = (schema.properties ?? {}) as Record<string, PropertyDef>;
  const required = new Set((schema.required ?? []) as string[]);

  let paramsMd = '';
  if (Object.keys(props).length > 0) {
    paramsMd =
      '\n## Parameters\n\n| Name | Type | Required | Description |\n|------|------|----------|-------------|\n';
    for (const [paramName, paramDef] of Object.entries(props)) {
      const paramType = paramDef.type ?? 'any';
      const paramDesc = paramDef.description ?? '-';
      const isReq = required.has(paramName) ? '✓' : '';
      paramsMd += `| \`${paramName}\` | ${paramType} | ${isReq} | ${paramDesc} |\n`;
    }
  }

  const firstLine = description.split('\n')[0] ?? '';

  // Generate Python binding name from qualified name (e.g., filesystem.read-file -> filesystem_binding.read-file)
  const bindingName = qualifiedName.replace('.', '_binding.');

  return `# ${qualifiedName}

> ${firstLine}

## Signature

\`\`\`python
await ${sig}
\`\`\`

## Description

${description}
${paramsMd}
## Usage Example

\`\`\`python
result = await ${bindingName}(
    # Add parameters here
)
\`\`\`
`;
};

const main = async () => {
  console.log('[list-tools] Starting tool schema dump...');

  // Initialize manager
  const manager = new MCPClientManager();
  await manager.initialize();

  // Clean and recreate tools directory
  try {
    await rm(TOOLS_DIR, { recursive: true, force: true });
  } catch {
    // ignore if doesn't exist
  }
  await mkdir(TOOLS_DIR, { recursive: true });

  // Get capabilities
  const caps = manager.getCapabilities();
  const toolsMap = caps.tools;

  // Group by server
  const servers = new Map<string, ToolData[]>();
  const allTools: ToolData[] = [];

  for (const [qualifiedName, toolInfo] of toolsMap.entries()) {
    const info = toolInfo as ToolInfo;
    let serverPrefix: string;
    let bareName: string;

    if (qualifiedName.includes('.')) {
      const idx = qualifiedName.indexOf('.');
      serverPrefix = qualifiedName.slice(0, idx);
      bareName = qualifiedName.slice(idx + 1);
    } else {
      serverPrefix = 'misc';
      bareName = qualifiedName;
    }

    const normalizedName = normalizeName(bareName);

    const toolData: ToolData = {
      qualifiedName: `${serverPrefix}.${normalizedName}`,
      serverPrefix,
      name: normalizedName,
      originalName: bareName,
      description: info.description ?? '',
      schema: (info.inputSchema ?? {}) as Record<string, unknown>,
    };

    if (!servers.has(serverPrefix)) {
      servers.set(serverPrefix, []);
    }
    servers.get(serverPrefix)!.push(toolData);
    allTools.push(toolData);
  }

  // Create directory structure
  for (const [serverName, serverTools] of servers.entries()) {
    const serverDir = path.join(TOOLS_DIR, serverName);
    await mkdir(serverDir, { recursive: true });

    // Create index.md for the server
    let indexContent = `# ${serverName.charAt(0).toUpperCase() + serverName.slice(1)} Tools\n\n`;
    indexContent += `This server provides ${serverTools.length} tools.\n\n`;
    indexContent += '## Available Tools\n\n';

    for (const tool of serverTools) {
      const descLine = (tool.description.split('\n')[0] ?? '').slice(0, 100);
      indexContent += `- [\`${tool.name}\`](./${tool.name}.md) - ${descLine}\n`;

      // Create individual tool .md file
      const mdPath = path.join(serverDir, `${tool.name}.md`);
      await writeFile(mdPath, generateToolMd(tool), 'utf-8');

      // Create individual tool .json file
      const jsonPath = path.join(serverDir, `${tool.name}.json`);
      await writeFile(jsonPath, JSON.stringify(tool, null, 2), 'utf-8');
    }

    // Write server index
    await writeFile(path.join(serverDir, 'index.md'), indexContent, 'utf-8');
    console.log(`[list-tools] Created ${serverTools.length} tools in tools/${serverName}/`);
  }

  // Write flat tools_schema.json for backwards compatibility
  await writeFile(
    path.resolve('tools_schema.json'),
    JSON.stringify(allTools, null, 2),
    'utf-8'
  );

  // Create tools/index.md
  let toolsIndex = '# MCP Tools Registry\n\n';
  toolsIndex += `Total: ${allTools.length} tools from ${servers.size} servers.\n\n`;
  toolsIndex += '## Servers\n\n';
  for (const [serverName, serverTools] of [...servers.entries()].sort((a, b) =>
    a[0].localeCompare(b[0])
  )) {
    toolsIndex += `- [\`${serverName}\`](./${serverName}/index.md) (${serverTools.length} tools)\n`;
  }

  await writeFile(path.join(TOOLS_DIR, 'index.md'), toolsIndex, 'utf-8');

  console.log(`[list-tools] === Done: ${allTools.length} tools from ${servers.size} servers ===`);
  console.log('[list-tools] Output: tools/ directory + tools_schema.json');

  // New: Trigger Ingestion to SQLite
  console.log('[list-tools] Syncing with Registry Database...');
  const { getToolRegistry } = await import('./tool_registry/index.js');
  const registry = getToolRegistry(TOOLS_DIR);
  // Force re-ingest
  registry.ingest(); 
  
  await manager.close();
};

main().catch((err) => {
  console.error('[list-tools] Failed:', err);
  process.exit(1);
});
