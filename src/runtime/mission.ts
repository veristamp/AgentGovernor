import { v4 as uuidv4 } from "uuid";
import type { RuntimeIdentity } from "./middleware";

export interface MissionRuntime {
	missionId: string;
	sessionId: string;
	identity: RuntimeIdentity;
}

export interface MissionRuntimeOptions {
	missionId?: string;
	sessionId?: string;
}

export function createMissionRuntime(
	identity: RuntimeIdentity,
	options: MissionRuntimeOptions = {},
): MissionRuntime {
	const missionId =
		options.missionId || identity.missionId || `mission-${uuidv4()}`;
	const sessionId =
		options.sessionId || identity.sessionId || `session-${uuidv4()}`;
	return {
		missionId,
		sessionId,
		identity: { ...identity, missionId, sessionId },
	};
}

export function createChildIdentity(
	parent: MissionRuntime,
	overrides: Partial<RuntimeIdentity> = {},
): RuntimeIdentity {
	return {
		...parent.identity,
		...overrides,
		missionId: parent.missionId,
		sessionId: parent.sessionId,
	};
}
