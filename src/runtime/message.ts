import { and, asc, desc, eq, gt } from "drizzle-orm";
import { v4 as uuidv4 } from "uuid";
import type { CoreMessage } from "./context";
import { db } from "../registry/db/db";
import { artifacts } from "../registry/db/schema";
import { saveArtifact } from "./trace";

export type ToolCall = {
  toolName: string;
  input?: unknown;
  toolCallId?: string;
};

export type ToolResult = {
  toolCallId: string;
  toolName: string;
  result: unknown;
};

export type MessagePart =
  | { type: "text"; text: string }
  | { type: "tool_call"; toolCallId: string; toolName: string; input: unknown }
  | {
      type: "tool_result";
      toolCallId: string;
      toolName: string;
      result: unknown;
    };

export type StoredMessage = {
  id: string;
  sessionId: string;
  role: "system" | "user" | "assistant" | "tool";
  parts: MessagePart[];
  createdAt: string;
};

export type LoopMessage = CoreMessage & {
  toolCalls?: ToolCall[];
};

const sessions = new Map<string, StoredMessage[]>();
const messages = new Map<string, StoredMessage>();

type CompactionRecord = {
  createdAt: string;
  summary: StoredMessage;
};

export const MessageStore = {
  async load(sessionId: string) {
    const cached = sessions.get(sessionId);
    if (cached && cached.length > 0) return cached;

    const compaction = await MessageStore.getCompaction(sessionId);
    const conditions = [
      eq(artifacts.sessionId, sessionId),
      eq(artifacts.type, "session_message"),
    ];
    if (compaction)
      conditions.push(gt(artifacts.createdAt, compaction.createdAt));

    const rows = await db
      .select()
      .from(artifacts)
      .where(and(...conditions))
      .orderBy(asc(artifacts.createdAt))
      .catch(() => []);

    const list = rows
      .map((row) => (row.content as { message?: StoredMessage }).message)
      .filter((msg): msg is StoredMessage => !!msg);

    const summary = compaction ? [compaction.summary] : [];
    const full = [...summary, ...list];
    sessions.set(sessionId, full);
    for (const message of full) messages.set(message.id, message);
    return full;
  },
  async ensureSystem(sessionId: string, text: string) {
    const list = sessions.get(sessionId) || [];
    const exists = list.some((msg) => msg.role === "system");
    if (exists) return;
    const message = MessageStore.createMessage(sessionId, "system", [
      { type: "text", text },
    ]);
    MessageStore.prependMessage(sessionId, message);
    await MessageStore.persist(message);
  },
  async addUser(sessionId: string, text: string) {
    return MessageStore.addMessage(sessionId, "user", [{ type: "text", text }]);
  },
  async addAssistant(sessionId: string, text: string, toolCalls: ToolCall[]) {
    const toolParts = toolCalls.map((call, index) => ({
      type: "tool_call" as const,
      toolCallId: call.toolCallId || `call_${Date.now()}_${index}`,
      toolName: call.toolName,
      input: call.input ?? {},
    }));
    return MessageStore.addMessage(sessionId, "assistant", [
      { type: "text", text },
      ...toolParts,
    ]);
  },
  async addToolResults(sessionId: string, results: ToolResult[]) {
    const parts = results.map((result) => ({
      type: "tool_result" as const,
      toolCallId: result.toolCallId,
      toolName: result.toolName,
      result: result.result,
    }));
    return MessageStore.addMessage(sessionId, "tool", parts);
  },
  list(sessionId: string) {
    return sessions.get(sessionId) || [];
  },
  toLoopMessages(sessionId: string): LoopMessage[] {
    const list = MessageStore.list(sessionId);
    return list.map((msg) => {
      const text = msg.parts
        .filter((part) => part.type === "text")
        .map((part) => part.text)
        .join("");

      if (msg.role === "assistant") {
        const toolCalls = msg.parts
          .filter((part) => part.type === "tool_call")
          .map((part) => ({
            toolCallId: part.toolCallId,
            toolName: part.toolName,
            input: part.input,
          }));
        return {
          role: "assistant",
          content: text,
          toolCalls: toolCalls.length > 0 ? toolCalls : undefined,
        };
      }

      if (msg.role === "tool") {
        const toolResults = msg.parts
          .filter((part) => part.type === "tool_result")
          .map((part) => ({
            type: "tool-result",
            toolCallId: part.toolCallId,
            toolName: part.toolName,
            result: part.result,
          }));
        return { role: "tool", content: toolResults };
      }

      return {
        role: msg.role,
        content: text,
      };
    });
  },
  async compact(
    sessionId: string,
    options?: { maxMessages?: number; keepLast?: number },
  ) {
    const list = sessions.get(sessionId) || [];
    const maxMessages = options?.maxMessages ?? 120;
    const keepLast = options?.keepLast ?? 40;
    if (list.length <= maxMessages) return;

    const systemIndex = list.findIndex((msg) => msg.role === "system");
    const system = systemIndex >= 0 ? list[systemIndex] : null;
    const startIndex = systemIndex >= 0 ? systemIndex + 1 : 0;
    const endIndex = Math.max(list.length - keepLast, startIndex);
    const removed = list.slice(startIndex, endIndex);
    const kept = list.slice(endIndex);

    const summaryText = MessageStore.summarize(removed);
    const summaryMessage = MessageStore.createMessage(sessionId, "assistant", [
      { type: "text", text: `[SUMMARY]\n${summaryText}` },
    ]);

    const next = system
      ? [system, summaryMessage, ...kept]
      : [summaryMessage, ...kept];
    MessageStore.replaceSession(sessionId, next);
    await MessageStore.saveCompaction(sessionId, summaryMessage);
  },
  async addMessage(
    sessionId: string,
    role: StoredMessage["role"],
    parts: MessagePart[],
  ) {
    const message = MessageStore.createMessage(sessionId, role, parts);
    MessageStore.appendMessage(sessionId, message);
    await MessageStore.persist(message);
    return message;
  },
  createMessage(
    sessionId: string,
    role: StoredMessage["role"],
    parts: MessagePart[],
  ) {
    return {
      id: uuidv4(),
      sessionId,
      role,
      parts,
      createdAt: new Date().toISOString(),
    } satisfies StoredMessage;
  },
  appendMessage(sessionId: string, message: StoredMessage) {
    const list = sessions.get(sessionId) || [];
    sessions.set(sessionId, [...list, message]);
    messages.set(message.id, message);
  },
  prependMessage(sessionId: string, message: StoredMessage) {
    const list = sessions.get(sessionId) || [];
    sessions.set(sessionId, [message, ...list]);
    messages.set(message.id, message);
  },
  replaceSession(sessionId: string, list: StoredMessage[]) {
    sessions.set(sessionId, list);
    for (const [id, message] of messages.entries()) {
      if (message.sessionId === sessionId) messages.delete(id);
    }
    for (const message of list) messages.set(message.id, message);
  },
  summarize(list: StoredMessage[]) {
    const textParts = list.flatMap((msg) =>
      msg.parts.map((part) => ({
        role: msg.role,
        part,
      })),
    );
    const lines = textParts.map((item) => {
      if (item.part.type === "text")
        return `${item.role.toUpperCase()}: ${item.part.text}`;
      if (item.part.type === "tool_call") {
        return `TOOL_CALL: ${item.part.toolName}`;
      }
      if (item.part.type === "tool_result") {
        return `TOOL_RESULT: ${item.part.toolName}`;
      }
      return "";
    });
    const summary = lines.filter((line) => line.length > 0).join("\n");
    return summary.slice(0, 8000);
  },
  async persist(message: StoredMessage) {
    await saveArtifact({
      type: "session_message",
      content: { message },
      sessionId: message.sessionId,
    });
  },
  async saveCompaction(sessionId: string, summary: StoredMessage) {
    await saveArtifact({
      type: "session_compaction",
      content: { summary },
      sessionId,
    });
  },
  async getCompaction(sessionId: string): Promise<CompactionRecord | null> {
    const row = await db
      .select()
      .from(artifacts)
      .where(
        and(
          eq(artifacts.sessionId, sessionId),
          eq(artifacts.type, "session_compaction"),
        ),
      )
      .orderBy(desc(artifacts.createdAt))
      .limit(1)
      .then((rows) => rows[0])
      .catch(() => undefined);
    if (!row) return null;
    const summary = (row.content as { summary?: StoredMessage }).summary;
    if (!summary) return null;
    return { createdAt: row.createdAt, summary };
  },
};
