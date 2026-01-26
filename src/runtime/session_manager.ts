import { getMissionService } from "../core/mission/service";
import { MessageStore, type ToolCall, type ToolResult } from "./message";

export type SessionManagerOptions = {
  sessionId: string;
  missionId?: string;
  runId?: string;
  runType?: "workflow" | "skill" | "tool" | "research";
  policyContext: {
    orgId: string;
    roles: string[];
    permissions: string[];
  };
};

export class SessionManager {
  readonly sessionId: string;
  readonly runId: string;
  private runStatus: "pending" | "running" | "completed" | "failed" = "pending";

  private constructor(sessionId: string, runId: string) {
    this.sessionId = sessionId;
    this.runId = runId;
  }

  static async start(options: SessionManagerOptions) {
    const service = getMissionService();
    const session = await service.getSession(options.sessionId);
    if (!session) {
      await service.createSession({
        id: options.sessionId,
        missionId: options.missionId,
        preloadContext: Boolean(options.missionId),
      });
    }
    const run = await service.createRun({
      id: options.runId,
      sessionId: options.sessionId,
      missionId: options.missionId,
      type: options.runType || "workflow",
      policyContext: options.policyContext,
    });
    await service.updateRunStatus(run.id, "running");
    await service.updateSessionState(options.sessionId, {});
    await MessageStore.load(options.sessionId);
    const manager = new SessionManager(options.sessionId, run.id);
    manager.runStatus = "running";
    return manager;
  }

  async ensureSystem(text: string) {
    await MessageStore.ensureSystem(this.sessionId, text);
  }

  async addUser(text: string) {
    await MessageStore.addUser(this.sessionId, text);
  }

  async addAssistant(text: string, toolCalls: ToolCall[]) {
    await MessageStore.addAssistant(this.sessionId, text, toolCalls);
  }

  async addToolResults(results: ToolResult[]) {
    await MessageStore.addToolResults(this.sessionId, results);
  }

  messages() {
    return MessageStore.toLoopMessages(this.sessionId);
  }

  async compact(options?: { maxMessages?: number; keepLast?: number }) {
    await MessageStore.compact(this.sessionId, options);
  }

  async finish(status: "completed" | "failed") {
    if (this.runStatus === status) return;
    this.runStatus = status;
    const service = getMissionService();
    await service.updateRunStatus(this.runId, status);
  }
}
