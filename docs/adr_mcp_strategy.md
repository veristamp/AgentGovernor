# Architectural Decision Record: MCP Integration Strategy

## 1. Direct MCP Tool Calling (via `@ai-sdk/mcp`)
**What it is:**
- The LLM directly "sees" the MCP tools as function definitions in its context window.
- The LLM generates arguments for these tools directly.
- The SDK/Client executes the tool call against the MCP server.

**Pros:**
- **Lowest Latency:** No intermediate steps. The model picks the tool, it executes.
- **Precision:** State-of-the-art models (Claude 3.5, GPT-4o) are highly optimized for direct tool calling.
- **Simplicity:** Less "glue code" to maintain for tool routing.

**Cons:**
- **Context Bloat:** If you have 50 MCP tools, injecting 50 JSON schemas into the system prompt consumes massive context tokens and degrades model reasoning.
- **Security:** Harder to inject granular policy checks *before* the tool execution if not careful (though middleware can handle this).
- **Complexity:** Requires "orchestrator" patterns to dynamically swap tool definitions in/out of context.

## 2. Managed / Discovery-Based Execution (Current System)
**What it is:**
- The LLM has a limited set of "meta-tools" (e.g., `skills.search`, `skills.run`).
- The LLM first *searches* for a capability, then *loads* it, then *executes* it (or delegates to a sub-agent).
- The "Kernel" (MCP Client Manager) mediates all calls behind a policy engine.

**Pros:**
- **Scalability:** Can support 10,000+ tools without context limit issues.
- **Security:** Centralized policy enforcement (Governance Layer) wrapping every execution.
- **Stability:** Prevents the model from getting confused by too many choices.

**Cons:**
- **Latency:** Requires multiple round-trips (Search -> Load -> Execute).
- **Complexity:** Complex "Agent Loop" logic to manage state and discovery.

## 3. Hybrid / "Just-in-Time" Strategy (Recommended)
**The "Sweet Spot":**
- **Core Tools:** Keep critical, high-frequency tools (filesystem, memory, basic reasoning) *always* loaded as native MCP tools for speed.
- **Discovery:** Keep the vast long-tail of specialized tools behind the discovery mechanism.
- **Dynamic Loading:** When the agent "discovers" a tool it needs via `skills.search`, *dynamically inject* that specific tool's schema into the LLM's active tool set for the remainder of the session.

## Comparison Table

| Feature | Direct MCP Calling | Managed Discovery | Hybrid (Recommended) |
| :--- | :--- | :--- | :--- |
| **Latency** | Low (1 step) | High (2-3 steps) | Variable (1-3 steps) |
| **Context Usage** | High (All tools loaded) | Low (Fixed meta-tools) | Optimized (Only active tools) |
| **Scalability** | Low (< 50 tools) | Unlimited | Unlimited |
| **Security** | Requires Middleware | Built-in by Design | Built-in via Wrapper |

## How to Proceed?

**Goal:** Increase efficiency without losing security.

**Proposal:**
1.  **Stick to your Managed Architecture** as the primary backbone. It is superior for robust, governed agents.
2.  **Optimize "Hot Paths":** Identify the top 5-10 most used tools (e.g., `fs.readFile`, `memory.recall`) and expose them *directly* via the Vercel AI SDK `tools` config in the `runGovernedLoop`.
    - This eliminates the "Search -> Load" overhead for 80% of operations.
3.  **Use Policy Wrappers:** Even for direct tools, wrap the `execute` function in your `PolicyEngine` (as you already do in `RuntimeFactory`).
4.  **Do NOT use `@ai-sdk/mcp` directly** if it bypasses your Governance Layer. instead, continue adapting your internal MCP Manager tools to the Vercel SDK format (as implemented in the refactor).

**Conclusion:**
You are correct to question direct usage. Your current "Kernel" approach is safer and more scalable. The optimization lies in **pre-loading common tools** directly into the `tools` array of `generateText` so the agent doesn't have to "discover" standard capabilities every time, while keeping specialized tools behind the discovery wall.
