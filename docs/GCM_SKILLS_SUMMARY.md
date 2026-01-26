# GCM Skills Architecture Summary

> **Status**: Design decisions captured. Ready for phased implementation.
> **Date**: 2026-01-14

---

## The Hierarchy (Final)

```
Tools (L0)     → Raw MCP capabilities (filesystem, memory, terminal, etc.)
Skills (L1)    → Governed wrappers, versioned, auth/policy enforced
Workflows (L2) → Python scripts that call skills (run in sandbox)
Missions (L3)  → Runtime container: state, audit, retries, budget
```

---

## Key Decisions Made

### 1. Skills are First-Class Citizens
- Skills are the primary interface for users/agents.
- Skills are exposed as MCP tools: `skills.<name>.<fn>`
- Skills go through Gate 2 (auth + policy + audit) like any other tool.

### 2. Option A: Strict Capability Boundary
- Users are granted skill permissions, NOT underlying tool permissions.
- Skills internally fan out to raw tools according to their manifest.
- This prevents privilege creep and keeps audit logs meaningful.

### 3. Skills are Versioned + Immutable
- Format: `skillId@version`
- New versions are published, not edited.
- Orgs/teams can pin to specific versions.

### 4. Sandbox Stays Python, Backend is TypeScript
- Workflows (Python) run in sandbox, call skills via JSON-RPC socket.
- Skills are implemented in TypeScript, exposed as MCP tools.
- Gate 1 (static auditor) checks Python code before execution.
- Gate 2 (MCPClientManager) enforces policy at runtime.

### 5. Local vs Central Access
- **Local repo**: Users can access their local filesystem freely (IDE/agent context).
- **Central/remote**: Policy + auth required (GitHub, shared repos, prod data).
- This is pragmatic: don't block local dev, govern shared resources.

### 6. Retrieval is Fuzzy, Execution is Deterministic
- KB (concepts + vectors) ranks skill/workflow candidates.
- Execution validates: skill exists, policy allows, inputs satisfied.
- No silent fallback to raw tools.

### 7. Don't Over-Optimize from the Start
- Start with what's built.
- Add governance incrementally.
- Avoid complex approval workflows until needed.

---

## What's Already Built

| Component | Location | Status |
|-----------|----------|--------|
| MCPClientManager | `src/mcp-client/manager.ts` | Working |
| Policy Engine | `src/policy/engine.ts` | Working |
| Auth SDK (JWT/JWKS) | `src/core/auth/` | Working |
| Socket Server | `src/socket-server/server.ts` | Working |
| Python Skill Loader | `sandbox/runtime/skill_loader.py` | Working (needs binding fix) |
| Python Skills | `skills/*/lib.py` | 3 skills exist |
| Tool Registry | `tools/` + `tools_schema.json` | Generated via `list_tools.py` |
| Static Auditor | `auditor/analyzer.py` + `src/audit/bridge.ts` | Working |
| Full Demo | `examples/gcm_full_demo.ts` | Working |

---

## What Needs Building (Phased)

### Phase 1: Fix Current Skill System (Immediate)
1. **Fix multi-binding issue in skill loader**
   - `skills/xlsx/lib.py` expects `filesystem` binding but gets `xlsx`
   - Update `sandbox/runtime/skill_loader.py` to support alias bindings

2. **Add skill manifest schema**
   - Create `skills/<name>/manifest.json` with:
     - `bindings`: `{ alias: serverPrefix }`
     - `version`: `1`
     - `fanoutTools`: `["filesystem.read_file", ...]`

3. **Validate manifest at load time**
   - Check bindings exist in `tools_schema.json`

### Phase 2: Skills as MCP Tools (Next)
1. **Create internal skill server in TS**
   - Expose skills as `skills.<name>.<fn>` tools
   - Route through MCPClientManager for policy enforcement

2. **Port Python skills to TS**
   - Start with `filesystem` skill (simplest)
   - Then `memory`, then `xlsx`

3. **Update socket protocol**
   - `skills.*` calls route to skill server
   - Raw tool calls route to MCP servers

### Phase 3: Skill Registry + KB Integration (Later)
1. **Skill registry table**
   - `skill_id`, `version`, `manifest`, `status`, `enabled_for_orgs`

2. **Ingest skills into KB**
   - Chunk `SKILL.md` files
   - Link to registry via stable IDs

3. **Deterministic selection loop**
   - Filter by org/team
   - Rank via KB
   - Validate before execution

---

## Immediate Next Steps (Do Now)

### Step 1: Fix the binding issue
Edit `sandbox/runtime/skill_loader.py` to read binding config from skill.

### Step 2: Add manifest.json to existing skills
Create `skills/filesystem/manifest.json`, `skills/memory/manifest.json`, `skills/xlsx/manifest.json`.

### Step 3: Run the existing demo
```bash
bun run examples/gcm_full_demo.ts
```
Verify Gate 1 + Gate 2 still work.

### Step 4: Port one skill to TS
Start with `skills.filesystem` as a TS module in `src/skills/filesystem.ts`.

---

## File Changes Made Today

| File | Change |
|------|--------|
| `src/mcp-client/manager.ts` | Added `requireActiveCheck`, `verifySignature` options |
| `src/mcp-client/indices.ts` | Added `getTool()`, `searchTools()` methods |
| `src/socket-server/server.ts` | Added `__search__`, `__inspect__`, `__context` support |
| `sandbox/runtime/discovery.py` | New file: discovery helpers for sandbox |

---

## Architecture Diagram (Simplified)

```
┌─────────────────────────────────────────────────────────────────┐
│  User Goal                                                       │
│       │                                                          │
│       ▼                                                          │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │  Skill/Workflow Selection (deterministic filter + KB rank)  │ │
│  └─────────────────────────────────────────────────────────────┘ │
│       │                                                          │
│       ▼                                                          │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │  Gate 1: Static Auditor                                      │ │
│  │  • Parse Python workflow                                     │ │
│  │  • Extract manifest (skills/tools it will call)              │ │
│  │  • Pre-check policy                                          │ │
│  └─────────────────────────────────────────────────────────────┘ │
│       │                                                          │
│       ▼                                                          │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │  Sandbox (Python)                                            │ │
│  │  • Runs workflow code                                        │ │
│  │  • Calls skills via mcp.use("skills.X.fn", ...)              │ │
│  └─────────────────────────────────────────────────────────────┘ │
│       │                                                          │
│       ▼                                                          │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │  Gate 2: MCPClientManager                                    │ │
│  │  • Validate JWT                                              │ │
│  │  • Check policy (RBAC)                                       │ │
│  │  • Route to skill server OR raw MCP server                   │ │
│  │  • Audit log                                                 │ │
│  └─────────────────────────────────────────────────────────────┘ │
│       │                                                          │
│       ▼                                                          │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │  Skill Server (TS) / MCP Servers                             │ │
│  │  • Execute skill logic                                       │ │
│  │  • Fan out to raw tools per manifest                         │ │
│  └─────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

---

## Principles to Keep

1. **Skills first, tools as implementation detail**
2. **Retrieval is fuzzy, execution is deterministic**
3. **Local dev is free, remote/shared is governed**
4. **Version and audit everything**
5. **Don't over-engineer; add complexity only when needed**

---

## References

- `docs/GOVERNED_CODE_MODE.md` — Full GCM architecture
- `docs/skill-talk.md` — Tools→Skills→Workflows→Missions philosophy
- `examples/gcm_full_demo.ts` — Working end-to-end demo
- `infra/FULL_INFRASTRUCTURE.md` — Complete system documentation
