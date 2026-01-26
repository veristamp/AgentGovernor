import { and, desc, eq } from "drizzle-orm";
import { v4 as uuidv4 } from "uuid";
import { db } from "../../registry/db/db";
import {
	missions,
	runs,
	sessions,
	traceEvents,
} from "../../registry/db/schema";
import type { EngramServiceImpl } from "../engram/service";
import type { NodePointer } from "../engram/types";

/**
 * Mission - A high-level goal with associated context
 *
 * In the GCM architecture, a Mission is the "Why":
 * - What is the user trying to accomplish?
 * - What capabilities are relevant?
 * - What context should be pre-loaded?
 *
 * The Mission orchestrates the "Switch-Brain" pattern:
 * - Engram provides the memory (knowledge graph)
 * - Session provides the execution state
 * - Agent provides the reasoning (RLM)
 */
export interface Mission {
	id: string;
	name: string;
	description?: string;
	ownerId: string;
	orgId: string;
	status: "active" | "completed" | "archived";
	createdAt: string;
	updatedAt: string;

	// Graph context - pre-identified relevant nodes
	contextPointers?: NodePointer[];
	relatedConcepts?: string[];
}

export interface Session {
	id: string;
	missionId: string | null;
	title?: string;

	// Persisted loop state
	state?: {
		// Current task context
		activeCapabilities?: string[]; // Loaded tool/skill IDs
		activeNodeIds?: number[]; // Loaded content from Engram

		// Planning state
		plan?: string[];
		currentStep?: number;

		// Draft artifacts
		draftCode?: string;
		draftWorkflow?: string;

		// Token tracking
		totalTokensUsed?: number;
		cachedTokens?: number;
	};

	createdAt: string;
	lastActiveAt: string;
}

export interface Run {
	id: string;
	sessionId: string;
	missionId?: string;
	type: "workflow" | "skill" | "tool" | "research";
	status: "pending" | "running" | "completed" | "failed";
	policyContext: {
		orgId: string;
		roles: string[];
		permissions: string[];
	};
	createdAt: string;
	endedAt?: string;
}

/**
 * Mission Service - Orchestrates the GCM Execution Model
 *
 * Key responsibilities:
 * 1. Create/manage Missions with graph-derived context
 * 2. Create/manage Sessions with Engram-backed state
 * 3. Track Runs and trace events for audit
 */
export class MissionService {
	private _missions = new Map<string, Mission>();
	private _sessions = new Map<string, Session>();
	private _engram?: EngramServiceImpl;

	setEngram(engram: EngramServiceImpl): void {
		this._engram = engram;
	}

	// =========================================================================
	// MISSIONS
	// =========================================================================

	/**
	 * Create a new Mission with optional Engram context discovery
	 */
	async createMission(params: {
		name: string;
		description?: string;
		ownerId: string;
		orgId: string;
		discoverContext?: boolean; // Use Engram to find relevant context
	}): Promise<Mission> {
		const id = `miss_${uuidv4()}`;
		const now = new Date().toISOString();

		// Optionally discover relevant context via Engram
		let contextPointers: NodePointer[] | undefined;
		let relatedConcepts: string[] | undefined;

		if (params.discoverContext && this._engram) {
			const contextQuery = `${params.name} ${params.description || ""}`;
			const result = await this._engram.search(contextQuery, 10);

			contextPointers = result.nodes
				.filter((n) => n.nodePointer)
				.map((n) => n.nodePointer!);
			relatedConcepts = result.relatedConcepts;
		}

		const mission: Mission = {
			id,
			name: params.name,
			description: params.description,
			ownerId: params.ownerId,
			orgId: params.orgId,
			status: "active",
			createdAt: now,
			updatedAt: now,
			contextPointers,
			relatedConcepts,
		};

		this._missions.set(id, mission);

		try {
			await db.insert(missions).values({
				id: mission.id,
				name: mission.name,
				description: mission.description,
				ownerId: mission.ownerId,
				orgId: mission.orgId,
				status: mission.status,
				createdAt: mission.createdAt,
				updatedAt: mission.updatedAt,
			});
		} catch (e) {
			console.error("Failed to persist mission:", e);
		}

		return mission;
	}

	async getMission(id: string): Promise<Mission | null> {
		if (this._missions.has(id)) {
			return this._missions.get(id)!;
		}

		try {
			const rows = await db
				.select()
				.from(missions)
				.where(eq(missions.id, id))
				.limit(1);

			if (rows.length > 0) {
				const m = rows[0]!;
				const mission: Mission = {
					id: m.id,
					name: m.name,
					description: m.description || undefined,
					ownerId: m.ownerId,
					orgId: m.orgId,
					status: m.status as Mission["status"],
					createdAt: m.createdAt,
					updatedAt: m.updatedAt,
				};
				this._missions.set(id, mission);
				return mission;
			}
		} catch (e) {
			console.error("Failed to fetch mission:", e);
		}
		return null;
	}

	async updateMissionContext(missionId: string): Promise<void> {
		const mission = await this.getMission(missionId);
		if (!mission || !this._engram) return;

		// Re-discover context
		const contextQuery = `${mission.name} ${mission.description || ""}`;
		const result = await this._engram.search(contextQuery, 10);

		mission.contextPointers = result.nodes
			.filter((n) => n.nodePointer)
			.map((n) => n.nodePointer!);
		mission.relatedConcepts = result.relatedConcepts;
		mission.updatedAt = new Date().toISOString();

		this._missions.set(missionId, mission);
	}

	async listMissions(orgId: string): Promise<Mission[]> {
		const memMissions = Array.from(this._missions.values()).filter(
			(m) => m.orgId === orgId,
		);

		try {
			const rows = await db
				.select()
				.from(missions)
				.where(eq(missions.orgId, orgId))
				.orderBy(desc(missions.updatedAt));

			for (const r of rows) {
				if (!this._missions.has(r.id)) {
					this._missions.set(r.id, {
						...r,
						status: r.status as Mission["status"],
						description: r.description || undefined,
					});
				}
			}
			return Array.from(this._missions.values()).filter(
				(m) => m.orgId === orgId,
			);
		} catch (e) {
			return memMissions;
		}
	}

	// =========================================================================
	// SESSIONS
	// =========================================================================

	/**
	 * Create a new Session, optionally pre-loading Mission context
	 */
	async createSession(params: {
		missionId?: string;
		title?: string;
		preloadContext?: boolean; // Pre-load Mission's Engram context
	}): Promise<Session> {
		const id = `sess_${uuidv4()}`;
		const now = new Date().toISOString();

		const state: Session["state"] = {};

		// Pre-load context from Mission if requested
		if (params.preloadContext && params.missionId) {
			const mission = await this.getMission(params.missionId);
			if (mission?.contextPointers) {
				state.activeNodeIds = mission.contextPointers.map((p) => p.id);
			}
		}

		const session: Session = {
			id,
			missionId: params.missionId || null,
			title: params.title,
			state,
			createdAt: now,
			lastActiveAt: now,
		};

		this._sessions.set(id, session);

		try {
			await db.insert(sessions).values({
				id: session.id,
				missionId: session.missionId,
				title: session.title,
				state: session.state,
				createdAt: session.createdAt,
				lastActiveAt: session.lastActiveAt,
			});
		} catch (e) {
			console.error("Failed to persist session:", e);
		}

		return session;
	}

	async getSession(id: string): Promise<Session | null> {
		if (this._sessions.has(id)) return this._sessions.get(id)!;

		try {
			const rows = await db
				.select()
				.from(sessions)
				.where(eq(sessions.id, id))
				.limit(1);

			if (rows.length > 0) {
				const s = rows[0]!;
				const session: Session = {
					id: s.id,
					missionId: s.missionId,
					title: s.title || undefined,
					state: (s.state as Session["state"]) || {},
					createdAt: s.createdAt,
					lastActiveAt: s.lastActiveAt,
				};
				this._sessions.set(id, session);
				return session;
			}
		} catch (e) {
			console.error("Failed to fetch session:", e);
		}

		return null;
	}

	/**
	 * Update session state (for persistence across requests)
	 */
	async updateSessionState(
		sessionId: string,
		stateUpdate: Partial<Session["state"]>,
	): Promise<void> {
		const session = await this.getSession(sessionId);
		if (!session) return;

		session.state = { ...session.state, ...stateUpdate };
		session.lastActiveAt = new Date().toISOString();

		this._sessions.set(sessionId, session);

		try {
			await db
				.update(sessions)
				.set({
					state: session.state,
					lastActiveAt: session.lastActiveAt,
				})
				.where(eq(sessions.id, sessionId));
		} catch (e) {
			console.error("Failed to update session:", e);
		}
	}

	/**
	 * Load Engram content for session's active nodes
	 */
	async loadSessionContext(
		sessionId: string,
	): Promise<Record<number, { content: string; docUrl: string }>> {
		const session = await this.getSession(sessionId);
		if (!session?.state?.activeNodeIds || !this._engram) {
			return {};
		}

		const content = await this._engram.loadContent(session.state.activeNodeIds);

		const result: Record<number, { content: string; docUrl: string }> = {};
		for (const [id, data] of Object.entries(content)) {
			result[Number(id)] = {
				content: data.content,
				docUrl: data.docUrl,
			};
		}
		return result;
	}

	async attachSessionToMission(
		sessionId: string,
		missionId: string,
	): Promise<boolean> {
		const session = await this.getSession(sessionId);
		if (!session) return false;

		const mission = await this.getMission(missionId);
		if (!mission) return false;

		session.missionId = missionId;
		session.lastActiveAt = new Date().toISOString();

		// Optionally inherit mission context
		if (mission.contextPointers) {
			session.state = session.state || {};
			session.state.activeNodeIds = mission.contextPointers.map((p) => p.id);
		}

		this._sessions.set(sessionId, session);

		try {
			await db
				.update(sessions)
				.set({
					missionId: missionId,
					state: session.state,
					lastActiveAt: session.lastActiveAt,
				})
				.where(eq(sessions.id, sessionId));
		} catch (e) {
			console.error("Failed to attach session:", e);
		}

		return true;
	}

	// =========================================================================
	// RUNS (Execution Tracking)
	// =========================================================================

	async createRun(params: {
		sessionId: string;
		missionId?: string;
		type: Run["type"];
		policyContext: Run["policyContext"];
	}): Promise<Run> {
		const id = `run_${uuidv4()}`;
		const now = new Date().toISOString();

		const run: Run = {
			id,
			sessionId: params.sessionId,
			missionId: params.missionId,
			type: params.type,
			status: "pending",
			policyContext: params.policyContext,
			createdAt: now,
		};

		try {
			await db.insert(runs).values({
				id: run.id,
				sessionId: run.sessionId,
				missionId: run.missionId || null,
				type: run.type,
				status: run.status,
				policyContext: run.policyContext,
				createdAt: run.createdAt,
				endedAt: null,
			});
		} catch (e) {
			console.error("Failed to persist run:", e);
		}

		return run;
	}

	async updateRunStatus(runId: string, status: Run["status"]): Promise<void> {
		const endedAt =
			status === "completed" || status === "failed"
				? new Date().toISOString()
				: undefined;

		try {
			await db.update(runs).set({ status, endedAt }).where(eq(runs.id, runId));
		} catch (e) {
			console.error("Failed to update run:", e);
		}
	}
}

// Singleton
let service: MissionService | null = null;

export function getMissionService(): MissionService {
	if (!service) service = new MissionService();
	return service;
}
