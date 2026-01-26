import { mkdir } from "node:fs/promises";
import { resolve } from "node:path";
import { getRolePermissionsAsync, matchesPermission } from "../policy/roles";
import type {
  SkillRegistry,
  SkillSummary,
} from "../../registry/skills/registry";
import type { ToolRegistry } from "../../registry/tools/registry";
import type { ToolDescriptor } from "../../registry/tools/types";
import type { WorkflowRegistry } from "../../registry/workflows/workflow_registry";
import type { EngramService } from "../engram/types";
import type { MCPClientManager } from "../mcp/manager";

export type CapabilityEntry = {
  id: string;
  type: "tool" | "skill" | "workflow";
  name: string;
  description: string;
  inputs?: string[];
  nodeId?: number;
  tokenCount?: number;
  loadName?: string;
  source: "engram" | "registry" | "mcp";
};

export type CapabilityIdentity = {
  orgId?: string;
  roles?: string[];
};

export type CapabilityLoadResult = {
  loaded?: boolean;
  capability?: Record<string, unknown>;
  _system_signal?: "load_tool" | "capability_loaded";
  toolName?: string;
  capabilityId?: string;
  error?: string;
  hint?: string;
  requiredPermission?: string;
};

type CapabilityCache = {
  generatedAt: string;
  items: CapabilityEntry[];
};

type CapabilityRegistryOptions = {
  engram?: EngramService;
  toolRegistry?: ToolRegistry;
  skillRegistry?: SkillRegistry;
  workflowRegistry?: WorkflowRegistry;
  mcp?: MCPClientManager;
  cacheDir?: string;
  cacheTtlMs?: number;
};

export class CapabilityRegistry {
  private cacheDir: string;
  private cacheTtlMs: number;
  private cacheByOrg = new Map<string, CapabilityCache>();
  private engram?: EngramService;
  private toolRegistry?: ToolRegistry;
  private skillRegistry?: SkillRegistry;
  private workflowRegistry?: WorkflowRegistry;
  private mcp?: MCPClientManager;

  constructor(options: CapabilityRegistryOptions) {
    this.engram = options.engram;
    this.toolRegistry = options.toolRegistry;
    this.skillRegistry = options.skillRegistry;
    this.workflowRegistry = options.workflowRegistry;
    this.mcp = options.mcp;
    this.cacheDir = resolve(options.cacheDir ?? ".gcm/cache");
    this.cacheTtlMs = options.cacheTtlMs ?? 5 * 60 * 1000;
  }

  async search(
    query: string,
    identity: CapabilityIdentity,
    options: { limit?: number; types?: string[] } = {},
  ): Promise<{ capabilities: CapabilityEntry[]; totalFound: number }> {
    const limit = options.limit ?? 5;
    const typeFilter = options.types?.length ? options.types : null;
    const cache = await this.loadCache(identity.orgId);
    const text = query.trim().toLowerCase();
    const cached = text.length
      ? cache.items.filter((item) => this.matches(item, text))
      : cache.items;

    const fromEngram = this.engram
      ? await this.searchEngram(query, identity)
      : [];

    const merged = this.mergeEntries([...cached, ...fromEngram]);
    const filtered = typeFilter
      ? merged.filter((item) => typeFilter.includes(item.type))
      : merged;

    return {
      capabilities: filtered.slice(0, limit),
      totalFound: filtered.length,
    };
  }

  async load(
    capabilityId: string,
    identity: CapabilityIdentity,
  ): Promise<CapabilityLoadResult> {
    const allowed = await this.isAllowed(identity, capabilityId);
    if (!allowed) {
      return {
        error: `Access denied to capability: ${capabilityId}`,
        requiredPermission: capabilityId,
      };
    }

    const normalized = capabilityId.replace(/^tools:/, "");
    const node = this.engram ? await this.engram.inspect(capabilityId) : null;
    if (node) {
      const toolName = node.type === "tool" ? node.name : undefined;
      return {
        loaded: true,
        capability: {
          id: node.id,
          type: node.type,
          name: node.name,
          description: node.description,
          structure: node.structure,
          relatedConcepts: node.relatedConcepts,
        },
        _system_signal: toolName ? "load_tool" : "capability_loaded",
        toolName,
        capabilityId,
      };
    }

    const tool = this.toolRegistry
      ? await this.toolRegistry.get(normalized)
      : null;
    const mcpTool = this.mcp
      ? this.mcp.getCapabilities().tools.get(normalized)
      : null;
    const skill = this.skillRegistry
      ? await this.skillRegistry.inspect(capabilityId)
      : null;
    const workflow = this.workflowRegistry
      ? await this.getWorkflow(capabilityId, identity.orgId)
      : null;

    if (tool || mcpTool) {
      const name = tool?.name || mcpTool?.name || normalized;
      return {
        loaded: true,
        capability: {
          id: capabilityId,
          type: "tool",
          name,
          description: tool?.description || mcpTool?.description || "",
          structure: tool?.schema || mcpTool?.inputSchema || {},
        },
        _system_signal: "load_tool",
        toolName: name,
        capabilityId,
      };
    }

    if (skill) {
      return {
        loaded: true,
        capability: {
          id: skill.skillRef,
          type: "skill",
          name: skill.skillId,
          description: skill.description,
          interfaces: skill.interfaces,
          examples: skill.examples ?? [],
          keywords: skill.keywords ?? [],
        },
        _system_signal: "capability_loaded",
        capabilityId,
      };
    }

    if (workflow) {
      return {
        loaded: true,
        capability: {
          id: `workflow:${workflow.metadata.id}`,
          type: "workflow",
          name: workflow.metadata.goal,
          description: workflow.metadata.summary || "",
          metadata: workflow.metadata,
        },
        _system_signal: "capability_loaded",
        capabilityId,
      };
    }

    return {
      error: `Capability not found: ${capabilityId}`,
      hint: "Use capability_search to find available capabilities",
    };
  }

  private async loadCache(orgId?: string): Promise<CapabilityCache> {
    const key = this.cacheKey(orgId);
    const cached = this.cacheByOrg.get(key);
    if (cached && !this.isStale(cached)) return cached;
    const file = this.cachePath(orgId);
    const fileHandle = Bun.file(file);
    const fromDisk = await fileHandle
      .exists()
      .then((exists) => (exists ? fileHandle.json() : null))
      .catch(() => null);
    if (fromDisk && !this.isStale(fromDisk as CapabilityCache)) {
      this.cacheByOrg.set(key, fromDisk as CapabilityCache);
      return fromDisk as CapabilityCache;
    }
    const refreshed = await this.refreshCache(orgId);
    this.cacheByOrg.set(key, refreshed);
    return refreshed;
  }

  private async refreshCache(orgId?: string): Promise<CapabilityCache> {
    const items: CapabilityEntry[] = [];
    const tools = this.toolRegistry ? await this.toolRegistry.getAll() : [];
    const skills = this.skillRegistry ? await this.skillRegistry.listAll() : [];
    const workflows = this.workflowRegistry
      ? await this.workflowRegistry.listWorkflows(orgId)
      : [];
    const mcpTools = this.mcp
      ? Array.from(this.mcp.getCapabilities().tools.values())
      : [];

    items.push(...tools.map((tool) => this.fromTool(tool)));
    items.push(...skills.map((skill) => this.fromSkill(skill)));
    items.push(
      ...workflows.map((workflow) => ({
        id: `workflow:${workflow.metadata.id}`,
        type: "workflow" as const,
        name: workflow.metadata.goal,
        description: workflow.metadata.summary || "",
        source: "registry" as const,
      })),
    );
    items.push(
      ...mcpTools.map((tool) => ({
        id: tool.name,
        type: "tool" as const,
        name: tool.name,
        description: tool.description || "",
        inputs: tool.inputSchema ? Object.keys(tool.inputSchema) : [],
        loadName: tool.name,
        source: "mcp" as const,
      })),
    );

    const merged = this.mergeEntries(items);
    const cache: CapabilityCache = {
      generatedAt: new Date().toISOString(),
      items: merged,
    };
    await this.persistCache(orgId, cache);
    return cache;
  }

  private async persistCache(
    orgId: string | undefined,
    cache: CapabilityCache,
  ) {
    const filePath = this.cachePath(orgId);
    const dir = resolve(this.cacheDir);
    await mkdir(dir, { recursive: true }).catch(() => undefined);
    await Bun.write(filePath, JSON.stringify(cache, null, 2));
  }

  private cachePath(orgId?: string) {
    const key = this.cacheKey(orgId);
    return resolve(this.cacheDir, `capabilities_${key}.json`);
  }

  private cacheKey(orgId?: string) {
    return (orgId || "personal").replace(/[^a-zA-Z0-9_-]/g, "_");
  }

  private isStale(cache: CapabilityCache) {
    const time = Date.parse(cache.generatedAt || "");
    if (!time) return true;
    return Date.now() - time > this.cacheTtlMs;
  }

  private matches(item: CapabilityEntry, query: string) {
    const haystack =
      `${item.id} ${item.name} ${item.description}`.toLowerCase();
    return haystack.includes(query);
  }

  private mergeEntries(items: CapabilityEntry[]) {
    const map = new Map<string, CapabilityEntry>();
    for (const item of items) {
      const key = `${item.type}:${item.id}`;
      if (!map.has(key)) map.set(key, item);
    }
    return Array.from(map.values());
  }

  private fromTool(tool: ToolDescriptor): CapabilityEntry {
    return {
      id: tool.qualifiedName,
      type: "tool",
      name: tool.name,
      description: tool.description,
      loadName: tool.name,
      source: "registry",
    };
  }

  private fromSkill(skill: SkillSummary): CapabilityEntry {
    return {
      id: skill.skillRef,
      type: "skill",
      name: skill.skillId,
      description: skill.description,
      inputs: skill.interfaces,
      source: "registry",
    };
  }

  private async searchEngram(query: string, identity: CapabilityIdentity) {
    if (!this.engram) return [] as CapabilityEntry[];
    const result = await this.engram.search(query, 10);
    const allowedNodes = await this.filterAllowed(result.nodes, identity);
    const entries: CapabilityEntry[] = [];
    for (const node of allowedNodes) {
      if (!this.isCapabilityType(node.type)) continue;
      entries.push({
        id: node.id,
        type: node.type,
        name: node.name,
        description: node.description,
        inputs: node.structure?.inputs
          ? Object.keys(node.structure.inputs)
          : [],
        nodeId: node.nodePointer?.id,
        tokenCount: node.nodePointer?.tokenCount || 0,
        loadName: node.type === "tool" ? node.name : undefined,
        source: "engram",
      });
    }
    return entries;
  }

  private async isAllowed(identity: CapabilityIdentity, id: string) {
    const roles = identity.roles ?? [];
    if (roles.includes("mcp:admin")) return true;
    const permissions = await getRolePermissionsAsync(roles, identity.orgId);
    return (
      matchesPermission(permissions, id) || matchesPermission(permissions, "*")
    );
  }

  private async filterAllowed<T extends { id: string }>(
    nodes: T[],
    identity: CapabilityIdentity,
  ) {
    const roles = identity.roles ?? [];
    if (roles.includes("mcp:admin")) return nodes;
    const permissions = await getRolePermissionsAsync(roles, identity.orgId);
    return nodes.filter(
      (node) =>
        matchesPermission(permissions, node.id) ||
        matchesPermission(permissions, "*"),
    );
  }

  private async getWorkflow(capabilityId: string, orgId?: string) {
    if (!this.workflowRegistry) return null;
    const id = capabilityId.replace(/^workflow:/, "");
    const list = await this.workflowRegistry.listWorkflows(orgId);
    return list.find((entry) => entry.metadata.id === id) || null;
  }

  private isCapabilityType(
    value: string,
  ): value is "tool" | "skill" | "workflow" {
    return value === "tool" || value === "skill" || value === "workflow";
  }
}
