import { mkdir } from "node:fs/promises";
import { join, resolve } from "node:path";
import { analyzeSkillCode } from "../../core/audit";
import type { MCPClientManager } from "../../core/mcp/manager";
import { getOrgPolicyPaths } from "../../core/policy/org_config";
import { SkillRegistry } from "../../registry/skills/registry";
import type {
  SkillExample,
  SkillFunctionSignature,
} from "../../registry/skills/schema";
import { ToolRegistry } from "../../registry/tools/registry";
import { createAgentRuntime, type RuntimeContext } from "../../runtime/factory";
import type { RuntimeIdentity } from "../../runtime/middleware";
import { runSubAgent } from "../../runtime/sub_agent";
import {
  createCapabilityLoaderTool,
  createCapabilitySearchTool,
} from "../../core/capabilities/discovery";
import { CapabilityRegistry } from "../../core/capabilities/registry";
import type { LlmClient } from "../main/llm_client";
import { createSkillCreatorLoopTools } from "./loop_tools";
import { retrieveRelevantTools } from "./tool_retriever";
import type {
  AbacRuleProposal,
  SkillCreationRequest,
  SkillCreationResult,
  SkillCreatorDependencies,
  SkillCreatorEvent,
  SkillCreatorOptions,
  SkillDraft,
  SkillDraftResponse,
} from "./types";

export class SkillCreatorAgent {
  private llm: LlmClient;
  private options: SkillCreatorOptions;

  constructor(
    dependencies: SkillCreatorDependencies,
    options: SkillCreatorOptions,
  ) {
    this.options = options;
    this.llm = dependencies.llm;
  }

  async run(
    request: SkillCreationRequest,
    dependencies: { mcp: MCPClientManager },
    onEvent?: (event: SkillCreatorEvent) => void,
  ): Promise<SkillCreationResult> {
    try {
      return await this.runWithAgentLoop(request, dependencies, onEvent);
    } catch (e) {
      console.warn("[SkillCreator] Agent loop failed:", e);
      throw e;
    }
  }

  private async runWithAgentLoop(
    request: SkillCreationRequest,
    dependencies: { mcp: MCPClientManager },
    onEvent?: (event: SkillCreatorEvent) => void,
  ): Promise<SkillCreationResult> {
    // 1. Context & Tools Setup
    const toolRegistry = new ToolRegistry();
    await toolRegistry.ingest();
    const skillRegistry = new SkillRegistry(this.options.skillsDir || "skills");
    await skillRegistry.ingest();

    const initialTools = await retrieveRelevantTools(
      request.goal,
      request.constraints || [],
      { toolsPath: this.options.toolsPath },
      12,
    );
    const initialSkills = await skillRegistry.search(request.goal, 6);

    const planState: { plan: string; execution_graph?: unknown } = { plan: "" };
    const loopTools = createSkillCreatorLoopTools({ planState });
    const capabilityRegistry = new CapabilityRegistry({
      toolRegistry,
      skillRegistry,
      mcp: dependencies.mcp,
    });
    const capabilityTools = [
      createCapabilitySearchTool({ registry: capabilityRegistry }),
      createCapabilityLoaderTool({ registry: capabilityRegistry }),
    ];

    const system = `You are the Skill Creator Orchestrator.
You will iteratively discover tools/skills, inspect schemas, refine a plan, then output a FINAL skill draft.

Skill requirements:
- Skills are higher-level orchestration graphs over MCP tools.
- You may use loops/branching/helpers and asyncio.gather for parallel fanout.
- All external side effects MUST go through provided tools via _bindings.
- Never use raw IO/network/process APIs (open, requests, aiohttp, httpx, urllib, socket, subprocess, os.system, etc.).

When done, return type=final with result matching the skill draft JSON schema:
{
  "skill_id": string,
  "summary": string,
  "interface": string[],
  "bindings": object,
  "fanout_tools": string[],
  "code": string,
  "examples": [{"code": string, "title"?: string, "description"?: string}],
  "dependencies"?: string[]
}
`;

    const user = `GOAL:\n${request.goal}\n\nCONSTRAINTS:\n${(request.constraints || []).map((c) => `- ${c}`).join("\n") || "- (none)"}\n\nINITIAL TOOL CANDIDATES (summaries):\n${initialTools.map((t) => `- ${t.qualifiedName}: ${t.description}`).join("\n") || "- (none)"}\n\nRELATED EXISTING SKILLS (summaries):\n${initialSkills.map((s) => `- ${s.skillRef}: ${s.description}`).join("\n") || "- (none)"}\n\nUse capability_search to find more tools/skills and system.load_capability to inspect them. Use update_plan as you refine.`;

    // 2. Identity & Model Setup
    // We trust the requester to provide valid identity info
    const missionId = request.requester.missionId || `mission-${Date.now()}`;
    const sessionId = request.requester.sessionId || `session-${Date.now()}`;
    const identity: RuntimeIdentity = {
      id: request.requester.id,
      type: "agent",
      orgId: request.requester.orgId,
      roles: request.requester.roles,
      scopes: [],
      missionId,
      sessionId,
    };

    // 3. Load Policy & Model
    // We assume policy engine is available or created here.
    const { PolicyEngine, DEFAULT_RULES } = await import(
      "../../core/policy/engine"
    );
    const policy = new PolicyEngine(DEFAULT_RULES);

    // HACK: Re-create OpenAI model (should be passed better)
    const { createOpenAI } = await import("@ai-sdk/openai");
    const openai = createOpenAI({ apiKey: process.env.OPENAI_API_KEY });
    const model = openai(this.options.model);

    // 4. Create Runtime with Custom Tools (Registry Access)
    // We create the runtime manually to inject our custom loop tools which are NOT standard MCP tools
    const ctx: RuntimeContext = {
      identity,
      mcp: dependencies.mcp,
      policy,
      model,
    };
    const runtime = await createAgentRuntime(ctx, []);
    runtime.tools = [...runtime.tools, ...capabilityTools, ...loopTools];

    // 5. Run Loop
    const runId = `skill-creator-run-${Date.now()}`;
    const { final } = await runSubAgent<SkillDraftResponse>({
      identity,
      mcp: dependencies.mcp,
      policy,
      model,
      system,
      user,
      allowedTools: [], // We injected them manually above
      runId,
      maxIterations: 10,
    });

    // 6. Validate & Finalize
    // Note: Validation should ideally happen inside the loop (validateFinal), but we can check here too
    // The `runSubAgent` above doesn't support custom validateFinal yet, so we trust the agent or fail here.
    // TODO: Enhance runSubAgent to support validateFinal or validation callback.

    if (!final || typeof final !== "object") {
      throw new Error("Agent did not return a valid object");
    }

    const skillDraft: SkillDraft = {
      skillId: final.skill_id,
      version: 1,
      summary: final.summary,
      interfaces: final.interface,
      bindings: final.bindings || {},
      fanoutTools: final.fanout_tools || [],
      code: final.code,
      examples: Array.isArray(final.examples) ? final.examples : [],
      dependencies: Array.isArray(final.dependencies) ? final.dependencies : [],
    };

    if (onEvent) onEvent({ type: "draft", draft: skillDraft });
    return await this.finalizeSkill(skillDraft, request);
  }

  private async finalizeSkill(
    draft: SkillDraft,
    request: SkillCreationRequest,
  ): Promise<SkillCreationResult> {
    if (!/^[a-z0-9][a-z0-9-_]*$/i.test(draft.skillId)) {
      throw new Error(
        `Invalid skillId '${draft.skillId}'. Use only letters, numbers, '-' and '_' (no 'skills:' or '@version').`,
      );
    }
    const paths = await getOrgPolicyPaths(request.requester.orgId);
    const audit = await analyzeSkillCode(draft.code, {
      configPath: paths.skillGateConfigPath,
    });
    if (!audit.allowed) {
      throw new Error(
        `Skill gate rejected ${draft.skillId}: ${audit.errors.join("; ")}`,
      );
    }
    const skillsDir = this.options.skillsDir || resolve("skills");
    const skillPath = join(skillsDir, draft.skillId);

    // 1. Create directory
    await mkdir(skillPath, { recursive: true });

    // 2. Write files
    await Bun.write(
      join(skillPath, "manifest.json"),
      JSON.stringify(
        {
          skillId: draft.skillId,
          version: draft.version,
          description: draft.summary,
          interfaces: draft.interfaces,
          bindings: draft.bindings,
          fanoutTools: draft.fanoutTools,
          ownerOrgId: request.requester.orgId,
          ownerTeamId: request.requester.teamId,
          createdBy: request.requester.id,
          visibility: request.requester.orgId ? "org" : "private",
        },
        null,
        2,
      ),
    );

    const examplesSection = this.formatExamplesMarkdown(
      draft.examples,
      draft.skillId,
      draft.interfaces,
    );
    await Bun.write(
      join(skillPath, "SKILL.md"),
      `# ${draft.skillId}\n\n${draft.summary}\n\n## Interface\n\n\`\`\`python\n${draft.interfaces.join("\n")}\n\`\`\`\n\n${examplesSection}`,
    );

    await Bun.write(join(skillPath, "lib.py"), draft.code);

    const functions = this.buildFunctionSignatures(draft.interfaces);
    const examples = this.ensureExamples(
      draft.examples,
      draft.skillId,
      draft.interfaces,
    );
    await Bun.write(
      join(skillPath, "signature.json"),
      JSON.stringify(
        {
          skillRef: `skills:${draft.skillId}@${draft.version}`,
          skillId: draft.skillId,
          version: String(draft.version),
          description: draft.summary,
          keywords: draft.skillId.split("-").filter(Boolean),
          functions,
          examples,
          dependencies: draft.dependencies ?? [],
        },
        null,
        2,
      ),
    );

    // 3. Update RBAC
    const rolePermissionsPath =
      this.options.rolePermissionsPath ||
      resolve("policy", "role_permissions.json");
    await this.updateRbac(
      rolePermissionsPath,
      request.requester.roles,
      draft.skillId,
      draft.version,
    );

    // 4. Create ABAC Proposal
    const abacProposal: AbacRuleProposal = {
      id: `allow-${draft.skillId}-${Date.now()}`,
      action: `skills:${draft.skillId}@${draft.version}`,
      conditions: {
        allowedOrgIds: request.requester.orgId
          ? [request.requester.orgId]
          : undefined,
        allowedTeamIds: request.requester.teamId
          ? [request.requester.teamId]
          : undefined,
      },
      priority: 10,
    };

    return {
      skillRef: `skills:${draft.skillId}@${draft.version}`,
      skillDir: skillPath,
      draft,
      rolesGranted: request.requester.roles,
      orgsGranted: request.requester.orgId ? [request.requester.orgId] : [],
      teamsGranted: request.requester.teamId ? [request.requester.teamId] : [],
      abacProposal,
    };
  }

  private buildFunctionSignatures(
    interfaces: string[],
  ): SkillFunctionSignature[] {
    return interfaces.map((signature) => {
      const cleaned = signature.replace(/^async\s+def\s+/i, "").trim();
      const name = cleaned.split("(")[0]?.trim() || cleaned;
      const paramsSection = cleaned.includes("(")
        ? cleaned.slice(cleaned.indexOf("(") + 1, cleaned.lastIndexOf(")"))
        : "";
      const params = paramsSection
        .split(",")
        .map((param) => param.trim())
        .filter(Boolean)
        .map((param) => {
          const beforeDefault = param.split("=")[0]?.trim() ?? "";
          const paramName = beforeDefault.split(":")[0]?.trim() ?? "";
          return {
            name: paramName || "param",
            type: "any" as const,
            required: !param.includes("="),
          };
        })
        .filter((param) => param.name !== "param");
      return {
        name,
        params,
      };
    });
  }

  private ensureExamples(
    examples: SkillExample[],
    skillId: string,
    interfaces: string[],
  ): SkillExample[] {
    const filtered = (examples || []).filter((e) => e.code.trim());
    if (filtered.length) {
      return filtered;
    }
    const method =
      interfaces[0]
        ?.split("(")[0]
        ?.replace(/^async\s+def\s+/i, "")
        .trim() || "method";
    return [
      {
        title: `Use ${skillId}`,
        code: `import skills\n\nasync def main():\n    result = await skills.load("${skillId}").${method}(...)\n    return result\n`,
      },
    ];
  }

  private formatExamplesMarkdown(
    examples: SkillExample[],
    skillId: string,
    interfaces: string[],
  ): string {
    const rendered = this.ensureExamples(examples, skillId, interfaces);
    const blocks = rendered.map((example) => {
      const title = example.title ? `### ${example.title}\n\n` : "";
      const description = example.description
        ? `${example.description}\n\n`
        : "";
      const code = example.code.trim();
      return `${title}${description}\`\`\`python\n${code}\n\`\`\``;
    });
    return `## Examples\n\n${blocks.join("\n\n")}`;
  }

  private async updateRbac(
    path: string,
    roles: string[],
    skillId: string,
    version: number,
  ) {
    let rbac: Record<string, string[]> = {};
    if (await Bun.file(path).exists()) {
      const content = await Bun.file(path).text();
      rbac = JSON.parse(content);
    }

    const skillRef = `skills:${skillId}@${version}`;
    let updated = false;

    for (const role of roles) {
      if (!rbac[role]) {
        rbac[role] = [];
      }
      if (!rbac[role].includes(skillRef)) {
        rbac[role].push(skillRef);
        updated = true;
      }
    }

    if (updated) {
      await Bun.write(path, JSON.stringify(rbac, null, 2));
    }
  }
}
