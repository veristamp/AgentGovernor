/**
 * Engram Module - The Neural Inode Table for GCM
 *
 * This module implements the "Switch-Brain" architecture:
 *
 * ┌─────────────────────────────────────────────────────────────────────────────┐
 * │                          GCM SWITCH-BRAIN ARCHITECTURE                       │
 * ├─────────────────────────────────────────────────────────────────────────────┤
 * │                                                                              │
 * │   ┌──────────────┐                      ┌──────────────┐                     │
 * │   │   MISSION    │ ←── "Why" ──────────→ │   ENGRAM     │                    │
 * │   │  (The Goal)  │                       │ (The Memory) │                    │
 * │   └──────┬───────┘                       └──────┬───────┘                    │
 * │          │                                      │                            │
 * │          │                                      │                            │
 * │          ▼                                      ▼                            │
 * │   ┌──────────────┐      ┌────────────┐   ┌──────────────┐                   │
 * │   │   SESSION    │ ←──→ │ POLICY GATE│ ←─│  GRAPH DB    │                   │
 * │   │  (The State) │      │  (Gate 2)  │   │ (Postgres)   │                   │
 * │   └──────┬───────┘      └────────────┘   └──────────────┘                   │
 * │          │                                                                   │
 * │          ▼                                                                   │
 * │   ┌──────────────────────────────────────────────────────────┐              │
 * │   │                    AGENT LOOP (RLM)                       │              │
 * │   │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐   │              │
 * │   │  │ kb.structure│→ │ kb.load     │→ │ execute/patch   │   │              │
 * │   │  │  (O(1))     │  │ (on-demand) │  │                 │   │              │
 * │   │  └─────────────┘  └─────────────┘  └─────────────────┘   │              │
 * │   └──────────────────────────────────────────────────────────┘              │
 * │                                                                              │
 * └─────────────────────────────────────────────────────────────────────────────┘
 *
 * Key Concepts:
 *
 * 1. ENGRAM (Conditional Memory)
 *    - The Graph DB exposed as an MCP Tool
 *    - Returns POINTERS (NodePointer), not content
 *    - O(1) structural lookups via getFileStructure()
 *    - On-demand content loading via loadContent()
 *
 * 2. HUB-HOP (Associative Memory)
 *    - Navigate via shared concepts, not file paths
 *    - Find related code across the entire codebase
 *    - Implements the "Soft Graph" pattern
 *
 * 3. MISSION (Goal Context)
 *    - High-level goal with pre-discovered context
 *    - Auto-discovers relevant nodes via Engram search
 *    - Persists context pointers for fast session startup
 *
 * 4. SESSION (Execution State)
 *    - Tracks active capabilities and loaded nodes
 *    - Persists state for resumable sessions
 *    - Inherits context from Mission
 *
 * Usage:
 *
 * ```typescript
 * import { getEngramService } from "./core/engram";
 * import { createEngramTools } from "./core/engram/mcp";
 * import { getMissionService } from "./core/mission";
 *
 * // 1. Get services
 * const engram = getEngramService();
 * const missionService = getMissionService();
 * missionService.setEngram(engram);
 *
 * // 2. Create MCP tools for agent
 * const engramTools = createEngramTools(engram);
 *
 * // 3. Create mission with auto-context discovery
 * const mission = await missionService.createMission({
 *     name: "Fix auth bug",
 *     description: "The refresh token is expiring too early",
 *     ownerId: "user_123",
 *     orgId: "org_456",
 *     discoverContext: true,  // Uses Engram to find relevant context
 * });
 *
 * // 4. Create session with pre-loaded context
 * const session = await missionService.createSession({
 *     missionId: mission.id,
 *     preloadContext: true,  // Pre-loads Mission's Engram context
 * });
 *
 * // 5. Agent uses tools
 * // Agent: kb.structure("auth.ts") → Gets file hierarchy (0 tokens)
 * // Agent: kb.load([123, 124]) → Loads specific nodes (~500 tokens)
 * // Agent: kb.hop(123) → Finds related via concepts
 * ```
 */

export { createEngramTools } from "./mcp";
export { EngramServiceImpl, getEngramService } from "./service";
export type {
	AccessDecision,
	AccessRequest,
	AccessResult,
	ContentResult,
	EngramLookupResult,
	EngramNode,
	EngramService,
	HubHopResult,
	NavigatorResult,
	NodePointer,
	NodeType,
	PolicyRule,
} from "./types";
