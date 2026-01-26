# Governed Code Mode: Agent Architecture (DIY & Layered)

## Core Philosophy: The "DIY" Agent
The fundamental goal of this architecture is to treat Agents not as hardcoded classes or frameworks, but as **composable configurations** running on top of a robust, governed kernel.

We adhere to a **Layered Abstraction** model. As we move up the layers, rigidity decreases and flexibility increases.

### The Stack

| Layer | Component | Responsibility | properties |
|-------|-----------|----------------|------------|
| **L3** | **DIY Agents** | Prompts, Tool Selections, specialized workflows. | *Ephemeral, Hot-swappable, Defined by text/config* |
| **L2** | **Runtime** | `runGovernedLoop`, `Mission`, `Session`, `SubAgent`. | *Orchestration, State Management, Composition* |
| **L1** | **Governance** | `PolicyEngine`, `RuntimeIdentity`, `AuditLogger`. | *Security, Access Control, Visibility* |
| **L0** | **Kernel** | `MCPClientManager`, `MissionService`, `Registry`, `Engram`. | *Capabilities, Persistence, System Calls, Structural Memory* |

## Key Concepts

### 1. Session vs. Mission
We strictly separate the **Conversational Context** from the **Execution Container**.

*   **Session (`sessionId`)**: 
    *   Represents a conversational thread (User ↔ Agent).
    *   Anchors the **Prompt Cache** (history, context).
    *   Stores trace events for debugging and user feedback.
    *   *Lifespan*: Ephemeral or persistent (chat log).

*   **Mission (`missionId`)**:
    *   Represents a governed unit of work/execution.
    *   Anchors **Policy**, **Budget**, and **Audit**.
    *   Can span multiple sessions (e.g., a long-running job checked by multiple users).
    *   *Lifespan*: Task-defined (until goal is met).

### 2. The DIY Agent Model & Recursive Discovery
An "Agent" in this system is simply:
1.  A **System Prompt** (Personality + Strategy).
2.  A set of **Tools** (Capabilities).
3.  A **Runtime Identity** (Permissions/Scope).

Crucially, agents do NOT need to have all tools loaded upfront. We use the **Recursive Discovery** pattern (aligned with Anthropic's Tool Search):

*   **Capability Search**: A unified tool (`capability_search`) that allows the agent to find Tools, Skills, and Workflows on demand.
*   **Deferred Loading**: The agent starts with minimal context and "pages in" capabilities as needed.

### 3. The "Grand Fusion" (Engram + RLM + GCM)
This architecture implements the "Grand Fusion" of concepts:

*   **Engram (KB Core)**: Exposed as `kb-core` MCP tools (or `registry.*` tools). It allows the agent to navigate the *structure* of code/knowledge (AST, Graph) without reading entire files, preventing context rot.
*   **RLM (Recursive Language Model)**: The Agent behaves like a Python REPL. It stitches together verified "Skills" (Python functions) and executes them in a sandbox. It does not hallucinate code from scratch; it orchestrates existing blocks.
*   **GCM (Governed Code Mode)**: The chassis that ensures every `mcp.use()` call is policy-checked against the Mission ID.

## Roadmap to Pure DIY
1.  **Unified Discovery Tool**: Implement `src/core/capabilities/discovery.ts` to replace hardcoded `searchWorkflows` / `searchSkills` logic.
2.  **Delete Legacy Wrappers**: Remove `OrchestratorAgent` class logic. The Orchestrator is just a loop with `capability_search` and `spawn_scout`.
3.  **Engram Integration**: Ensure the `kb-core` (or equivalent) tools are discoverable via the registry so the RLM can "hop" through the codebase structure.
