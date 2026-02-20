import { desc, eq } from "drizzle-orm";
import { v4 as uuidv4 } from "uuid";
import { db } from "../registry/db/db";
import { artifacts, runs, sessions, traceEvents } from "../registry/db/schema";

export interface TraceEvent {
	id: string;
	runId?: string;
	sessionId?: string;
	iteration: number;
	type: "plan" | "tool_call" | "tool_result" | "error" | "final" | "event";
	content: Record<string, unknown>;
	reasoning?: string;
	tokenCount?: number;
	createdAt: string;
}

export class TraceManager {
	private _runId?: string;
	private _sessionId?: string;
	private _memoryEvents: TraceEvent[] = []; // In-memory fallback

	get runId() {
		return this._runId;
	}
	get sessionId() {
		return this._sessionId;
	}

	constructor(opts: { runId?: string; sessionId?: string }) {
		this._runId = opts.runId;
		this._sessionId = opts.sessionId;
	}

	public async emit(
		event: Omit<TraceEvent, "id" | "runId" | "sessionId" | "createdAt">,
	) {
		const id = uuidv4();
		const createdAt = new Date().toISOString();

		const traceEvent: TraceEvent = {
			id,
			runId: this._runId,
			sessionId: this._sessionId,
			iteration: event.iteration,
			type: event.type,
			content: event.content,
			reasoning: event.reasoning,
			tokenCount: event.tokenCount,
			createdAt,
		};

		// Always store in memory as backup/primary if DB fails
		this._memoryEvents.push(traceEvent);

		try {
			await db.insert(traceEvents).values({
				id,
				runId: this._runId,
				sessionId: this._sessionId,
				iteration: String(event.iteration),
				type: event.type,
				content: event.content,
				reasoning: event.reasoning,
				tokenCount: event.tokenCount ? String(event.tokenCount) : undefined,
				createdAt,
			});
		} catch {
			// Swallow DB error and rely on memory for this session
		}

		return id;
	}

	public async getRecentEvents(limit = 50): Promise<TraceEvent[]> {
		// Try DB first
		try {
			if (!this._runId && !this._sessionId) return [];

			const condition = this._runId
				? eq(traceEvents.runId, this._runId)
				: eq(traceEvents.sessionId, this._sessionId as string);

			const rows = await db
				.select()
				.from(traceEvents)
				.where(condition)
				.orderBy(desc(traceEvents.createdAt))
				.limit(limit);

			if (rows.length > 0) {
				return rows.map((r) => ({
					id: r.id,
					runId: r.runId || undefined,
					sessionId: r.sessionId || undefined,
					iteration: Number(r.iteration),
					type: r.type as TraceEvent["type"],
					content: r.content as Record<string, unknown>,
					reasoning: r.reasoning || undefined,
					tokenCount: r.tokenCount ? Number(r.tokenCount) : undefined,
					createdAt: r.createdAt,
				}));
			}
		} catch {
			// DB failed or empty
		}

		// Fallback to memory
		return [...this._memoryEvents].reverse().slice(0, limit);
	}
}

export async function createRun(params: {
	sessionId?: string;
	missionId?: string;
	type: string;
	policyContext: Record<string, unknown>;
}) {
	const id = uuidv4();
	const now = new Date().toISOString();
	await db.insert(runs).values({
		id,
		sessionId: params.sessionId,
		missionId: params.missionId,
		type: params.type,
		status: "pending",
		policyContext: params.policyContext,
		createdAt: now,
	});
	return id;
}

export async function createSession(params: {
	missionId?: string;
	title?: string;
	state?: Record<string, unknown>;
}) {
	const id = uuidv4();
	const now = new Date().toISOString();
	await db.insert(sessions).values({
		id,
		missionId: params.missionId,
		title: params.title,
		state: params.state || {},
		createdAt: now,
		lastActiveAt: now,
	});
	return id;
}

export async function saveArtifact(params: {
	type: string;
	content: Record<string, unknown>;
	sessionId?: string;
	parentId?: string;
}) {
	const id = uuidv4();
	const now = new Date().toISOString();
	await db.insert(artifacts).values({
		id,
		type: params.type,
		content: params.content,
		parentId: params.parentId,
		sessionId: params.sessionId,
		createdAt: now,
	});
	return id;
}
