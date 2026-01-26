import type { TraceEvent } from "./trace";

// Compatible with Vercel AI SDK Core message format
export type CoreMessage =
  | { role: "system"; content: string }
  | { role: "user"; content: string | Array<any> }
  | { role: "assistant"; content: string | Array<any> }
  | { role: "tool"; content: Array<any> };

export class ContextManager {
  private maxTokens: number;
  private reserveTokens: number;

  constructor(maxTokens = 128000, reserveTokens = 4000) {
    this.maxTokens = maxTokens;
    this.reserveTokens = reserveTokens;
  }

  public compose(params: {
    system: string;
    initialUser?: string;
    history: TraceEvent[];
  }): CoreMessage[] {
    const messages: CoreMessage[] = [];
    let currentTokens = 0;
    const budget = this.maxTokens - this.reserveTokens;

    // 1. System Prompt (Priority #1)
    const sysMsg: CoreMessage = { role: "system", content: params.system };
    messages.push(sysMsg);
    currentTokens += this.estimateTokens(params.system);

    // 2. Initial User Message (Priority #2)
    if (params.initialUser) {
      const tokens = this.estimateTokens(params.initialUser);
      let content = params.initialUser;

      if (currentTokens + tokens > budget) {
        // Truncate if massively huge
        content =
          content.slice(0, (budget - currentTokens) * 4) + "... (truncated)";
      }

      messages.push({ role: "user", content });
      currentTokens += this.estimateTokens(content);
    }

    // 3. History / Trace Events (Priority #3, Newest First)
    // We work backwards from the most recent event
    const contextMessages: CoreMessage[] = [];
    // Clone and reverse to process newest -> oldest
    const reversedHistory = [...params.history].reverse();

    for (const event of reversedHistory) {
      // Convert TraceEvent to CoreMessage
      const msg = this.traceToMessage(event);
      if (!msg) continue;

      // Estimate tokens (approximate for objects)
      const contentStr =
        typeof msg.content === "string"
          ? msg.content
          : JSON.stringify(msg.content);

      const tokens = this.estimateTokens(contentStr);

      if (currentTokens + tokens <= budget) {
        contextMessages.unshift(msg);
        currentTokens += tokens;
      } else if (currentTokens + 100 <= budget) {
        // Try to summarize/compress if near limit
        const summary = this.summarizeEvent(event);
        const sumContentStr =
          typeof summary.content === "string"
            ? summary.content
            : JSON.stringify(summary.content);
        const sumTokens = this.estimateTokens(sumContentStr);

        if (currentTokens + sumTokens <= budget) {
          contextMessages.unshift(summary);
          currentTokens += sumTokens;
        } else {
          break; // Full
        }
      } else {
        break; // Full
      }
    }

    return [...messages, ...contextMessages];
  }

  // Simple heuristic: 4 chars ~= 1 token
  private estimateTokens(text: string): number {
    return Math.ceil(text.length / 4);
  }

  private traceToMessage(event: TraceEvent): CoreMessage | null {
    const toolCallId =
      typeof event.content.toolCallId === "string"
        ? event.content.toolCallId
        : `call_${event.iteration}`;
    switch (event.type) {
      case "plan":
        return {
          role: "assistant",
          content: `THOUGHT: ${event.content.plan || event.reasoning}`,
        };
      case "tool_call":
        return {
          role: "assistant",
          content: [
            {
              type: "tool-call",
              toolCallId,
              toolName: event.content.name,
              args: event.content.arguments,
            },
          ],
        };
      case "tool_result":
        return {
          role: "tool",
          content: [
            {
              type: "tool-result",
              toolCallId,
              toolName: event.content.name,
              result: event.content.result,
            },
          ],
        };
      case "error":
        return {
          role: "user", // Errors act as system/user feedback
          content: `ERROR: ${event.content.error}`,
        };
      case "final":
        return {
          role: "assistant",
          content: JSON.stringify(event.content.result),
        };
      default:
        return null;
    }
  }

  private summarizeEvent(event: TraceEvent): CoreMessage {
    if (event.type === "tool_result") {
      const toolCallId =
        typeof event.content.toolCallId === "string"
          ? event.content.toolCallId
          : `call_${event.iteration}`;
      return {
        role: "tool",
        content: [
          {
            type: "tool-result",
            toolCallId,
            toolName: event.content.name,
            result: "(Output truncated to save memory)",
          },
        ],
      };
    }
    // Default fallback
    const msg = this.traceToMessage(event);
    return msg || { role: "assistant", content: "..." };
  }
}
