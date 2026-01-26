import { streamText } from "ai";
import { z } from "zod";
import type { AgentRuntime, RuntimeContext } from "./factory";
import { type TraceEvent, TraceManager } from "./trace";
import type {
  AgentLoopRunOptions,
  AgentLoopTool,
  AgentLoopToolContext,
} from "./types";
import { type ToolCall, type ToolResult } from "./message";
import { SessionManager } from "./session_manager";

export interface GovernedLoopOptions extends AgentLoopRunOptions {
  runId?: string;
  sessionId?: string;
  runType?: "workflow" | "skill" | "tool" | "research";
  compaction?: {
    maxMessages?: number;
    keepLast?: number;
  };
  validateFinal?: (
    value: unknown,
  ) =>
    | { ok: true; value: unknown }
    | { ok: false; error: string }
    | Promise<{ ok: true; value: unknown } | { ok: false; error: string }>;
}

/**
 * Creates an executable AgentLoopTool from a name and RuntimeContext.
 * Used for dynamic tool loading.
 */
function createToolWrapper(
  name: string,
  ctx: RuntimeContext,
): AgentLoopTool | null {
  const capabilities = ctx.mcp.getCapabilities();
  const toolDef = capabilities.tools.get(name);
  if (!toolDef) return null;

  return {
    name: toolDef.name,
    description: toolDef.description || "",
    inputSchema: toolDef.inputSchema ?? {},
    execute: async (
      args: Record<string, unknown>,
      _toolCtx: AgentLoopToolContext,
    ) => {
      return await ctx.mcp.executeAction(
        {
          actionType: "tool",
          actionName: name,
          arguments: args,
        },
        {
          identityId: ctx.identity.id,
          orgId: ctx.identity.orgId,
          roles: ctx.identity.roles,
          scopes: ctx.identity.scopes,
          missionId: ctx.identity.missionId,
          sessionId: ctx.identity.sessionId,
        },
      );
    },
  };
}

export async function runGovernedLoop<TFinal = string>(
  ctx: RuntimeContext,
  runtime: AgentRuntime,
  systemPrompt: string,
  userPrompt: string,
  options: GovernedLoopOptions = {},
): Promise<{
  final: TFinal;
  iterations: number;
  trace: TraceEvent[];
}> {
  const maxIterations = options.maxIterations ?? 10;
  const sessionId = options.sessionId || ctx.identity.sessionId;
  const session = await SessionManager.start({
    sessionId,
    missionId: ctx.identity.missionId,
    runId: options.runId,
    runType: options.runType,
    policyContext: {
      orgId: ctx.identity.orgId || "",
      roles: ctx.identity.roles,
      permissions: ctx.identity.scopes,
    },
  });
  const traceManager = new TraceManager({
    runId: session.runId,
    sessionId: session.sessionId,
  });

  console.log(`[Loop] Starting run (Session: ${traceManager.sessionId})`);
  await session.ensureSystem(systemPrompt);
  await session.addUser(userPrompt);

  let currentIteration = 0;
  let finished = false;
  let finalValue: unknown = null;

  try {
    while (currentIteration < maxIterations && !finished) {
      const iteration = currentIteration;

      // 1. Prepare Tools (Re-evaluate every loop to capture dynamic additions)
      const sdkTools: Record<string, any> = {};
      const nameMap = new Map<string, string>();
      const reverseNameMap = new Map<string, string>();

      for (const t of runtime.tools) {
        let safeName = t.name.replace(/[^a-zA-Z0-9_-]/g, "_");
        let suffix = 1;
        while (reverseNameMap.has(safeName)) {
          safeName = `${safeName}_${suffix}`;
          suffix += 1;
        }
        nameMap.set(t.name, safeName);
        reverseNameMap.set(safeName, t.name);

        sdkTools[safeName] = {
          description: t.description,
          parameters: z.object({}).passthrough(), // AI SDK uses 'parameters' or 'inputSchema'? Using z object for safety
          // We do NOT attach 'execute' here because we want manual control.
          // Vercel AI SDK 'generateText' will simply return the tool call if execute is missing/optional?
          // Actually, if we provide tools to generateText, it expects them to be "Tool" objects from the SDK.
          // We will execute manually.
        };
      }

      await session.compact({
        maxMessages: options.compaction?.maxMessages ?? 120,
        keepLast: options.compaction?.keepLast ?? 40,
      });
      const messages = session.messages();
      const stream = streamText({
        model: runtime.model,
        tools: sdkTools,
        // @ts-expect-error - maxSteps is supported in AI SDK but types might be stale
        maxSteps: 1,
        messages: messages,
      });

      const textResult = await Promise.resolve(stream.text)
        .then((value) => ({ ok: true as const, value }))
        .catch((error: unknown) => ({
          ok: false as const,
          error: String(error),
        }));

      if (!textResult.ok) {
        await traceManager.emit({
          iteration,
          type: "error",
          content: { error: textResult.error },
        });
        throw new Error(textResult.error);
      }

      const text = textResult.value;
      const toolCalls = await stream.toolCalls;
      const calls = (toolCalls || []).map((call) => ({
        toolName: call.toolName,
        input: call.input,
        toolCallId: call.toolCallId,
      }));

      await session.addAssistant(text || "", calls);

      if (calls.length > 0) {
        const toolResults: ToolResult[] = [];
        const timeoutMs = options.toolCallTimeoutMs;
        const execute = async (call: ToolCall, index: number) => {
          const originalName =
            reverseNameMap.get(call.toolName) || call.toolName;
          const toolImpl = runtime.tools.find((t) => t.name === originalName);
          const callId =
            typeof call.toolCallId === "string"
              ? call.toolCallId
              : `call_${iteration}_${index}`;
          const args =
            call.input && typeof call.input === "object"
              ? (call.input as Record<string, unknown>)
              : {};

          const callPromise = toolImpl
            ? toolImpl.execute(args, {
                orgId: ctx.identity.orgId,
                roles: ctx.identity.roles,
                scopes: ctx.identity.scopes,
                missionId: ctx.identity.missionId,
                sessionId: ctx.identity.sessionId,
              })
            : Promise.resolve(`Error: Tool ${originalName} not found`);

          const timeoutPromise = timeoutMs
            ? new Promise((_, reject) => {
                setTimeout(
                  () => reject(new Error(`Tool timeout: ${originalName}`)),
                  timeoutMs,
                );
              })
            : callPromise;

          const outputResult = await Promise.race([callPromise, timeoutPromise])
            .then((value) => ({ ok: true as const, value }))
            .catch((error: unknown) => ({
              ok: false as const,
              error: String(error),
            }));

          const output = outputResult.ok
            ? outputResult.value
            : `Error: ${outputResult.error}`;

          await traceManager.emit({
            iteration,
            type: "tool_call",
            content: {
              name: originalName,
              arguments: args,
              toolCallId: callId,
            },
            reasoning: text,
          });

          await traceManager.emit({
            iteration,
            type: "tool_result",
            content: {
              name: originalName,
              result: output,
              toolCallId: callId,
            },
          });

          const outputObject =
            output && typeof output === "object"
              ? (output as {
                  _system_signal?: string;
                  toolName?: string;
                  capabilityId?: string;
                })
              : null;
          const signal = outputObject?._system_signal;
          const shouldLoad =
            signal === "load_tool" ||
            (signal === "capability_loaded" && !!outputObject?.toolName);
          if (shouldLoad) {
            const newToolName = outputObject?.toolName || "";
            console.log(`[Loop] Dynamically loading tool: ${newToolName}`);
            const newTool = createToolWrapper(newToolName, ctx);
            const loaded =
              newTool && !runtime.tools.some((t) => t.name === newTool.name);
            if (loaded && newTool) runtime.tools.push(newTool);
            const systemMessage = loaded
              ? `System: Tool '${newToolName}' loaded successfully. You can now use it.`
              : `System: Failed to load tool '${newToolName}'. It may not exist or access is denied.`;
            return {
              toolCallId: callId,
              toolName: call.toolName,
              result: systemMessage,
            };
          }

          if (!outputResult.ok) {
            await traceManager.emit({
              iteration,
              type: "error",
              content: { error: outputResult.error, tool: originalName },
            });
          }

          return {
            toolCallId: callId,
            toolName: call.toolName,
            result: output,
          };
        };

        const results = await Promise.all(
          calls.map((call, index) => execute(call, index)),
        );

        for (const r of results) {
          toolResults.push({
            toolCallId: r.toolCallId,
            toolName: r.toolName,
            result: r.result,
          });
        }
        await session.addToolResults(toolResults);
      }

      if (calls.length === 0) {
        finalValue = text;
        const parsed = (() => {
          const clean = (text || "").trim();
          const isJson = clean.startsWith("{") || clean.startsWith("[");
          if (isJson) return JSON.parse(clean);
          const jsonMatch =
            clean.match(/```json\n([\s\S]*?)\n```/) ||
            clean.match(/```\n([\s\S]*?)\n```/);
          if (jsonMatch && jsonMatch[1]) return JSON.parse(jsonMatch[1]);
          return undefined;
        })();

        const parsedValue = parsed === undefined ? finalValue : parsed;
        finalValue = parsedValue;

        const validated = options.validateFinal
          ? await options.validateFinal(finalValue)
          : ({ ok: true as const, value: finalValue } as const);

        if (!validated.ok) {
          await traceManager.emit({
            iteration,
            type: "error",
            content: { error: validated.error },
          });
          throw new Error(`Validation Failed: ${validated.error}`);
        }

        finalValue = validated.value;
        finished = true;
      }

      await session.compact({
        maxMessages: options.compaction?.maxMessages ?? 120,
        keepLast: options.compaction?.keepLast ?? 40,
      });
      currentIteration++;
    }
  } catch (e) {
    await session.finish("failed");
    throw e;
  }

  if (!finished) {
    console.warn("[Loop] Max iterations reached");
  }

  await traceManager.emit({
    iteration: currentIteration,
    type: "final",
    content: { result: finalValue },
  });
  await session.finish("completed");

  return {
    final: finalValue as TFinal,
    iterations: currentIteration,
    trace: await traceManager.getRecentEvents(100),
  };
}
