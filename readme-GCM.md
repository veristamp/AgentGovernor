# Governed Code Mode (GCM)

Governed Code Mode is a security-first agent runtime for executing LLM-authored automation without giving the model raw access to your machine, networks, or credentials.

Instead of trusting an LLM to run arbitrary code, GCM enforces **governance by architecture**:

- The model produces **Python workflow code** (easy for small/local models to generate).
- The workflow is **statically audited** to derive what it will do (Gate 1).
- The workflow executes inside a **sandbox** with **no network** and no direct access to secrets.
- Every external operation goes through a **policy-enforced tool gateway** (Gate 2).

This repository still contains legacy YAML planning work, but **GCM is the current direction**: skills-first, code in a sandbox, deterministic enforcement, and auditable execution.

---

## The Vision

GCM is designed to be the execution substrate for “real agents” in real environments:

- **Zero-trust execution**: treat model output as untrusted input.
- **Skills-first interface**: users and agents get permissions to **skills**, not raw tools.
- **Deterministic enforcement**: retrieval can be fuzzy; execution must be strict.
- **Versioned, immutable capabilities**: skills are pinned by `skillId@version` and published as new versions.
- **Separation of concerns**:
  - LLM proposes an action (code)
  - the system derives intent (manifest)
  - policy decides if it is allowed
  - sandbox executes safely

The long-term goal is a hierarchy of increasing structure:

```
Tools (L0)     → Raw MCP capabilities (filesystem, memory, terminal, etc.)
Skills (L1)    → Governed wrappers, versioned, policy-enforced
Workflows (L2) → Python scripts that call skills (run in sandbox)
Missions (L3)  → Runtime container: state, audit, retries, budget
```

---

## Why This Approach

Modern “code mode” agents are powerful but unsafe:

- They often rely on `eval()`-like execution.
- They mix planning + execution.
- They expose credentials and system resources to the model.

GCM takes the opposite stance:

- Let the LLM generate **simple code**.
- Treat that code as **untrusted**.
- Require it to pass deterministic gates before it touches anything real.

---

## Architecture (Double-Gated Security)

GCM uses two independent gates:

### Gate 1: Static Auditor (Pre-Execution)

Before the workflow runs, we parse the Python AST and derive a manifest of what the code will do:

- tools/skills invoked
- static arguments where possible
- presence of loops/conditionals
- other safety signals

This prevents “surprise tool calls” from reaching runtime.

Key implementation:
- `auditor/analyzer.py`
- `src/audit/bridge.ts` (TypeScript bridge that runs the analyzer)

### Gate 2: Runtime Policy + Tool Gateway

Even if a workflow passes Gate 1, every call is checked again at runtime:

- identity validation (JWT/JWKS)
- revocation / kill switch
- RBAC + ABAC policy checks
- secrets injection at the edge (sandbox never sees secrets)
- audit trail

Key implementation:
- `src/mcp-client/manager.ts`
- `src/policy/engine.ts`
- `src/socket-server/*`

---

## Skills (The Unit of Governance)

Skills are governed wrappers around raw MCP tools.

A skill is:
- **Versioned**: `skills:<skillId>@<version>`
- **Immutable**: publish a new version, don’t edit in-place
- **Bounded**: it can only call tools listed in its manifest

### Skill Format

Each skill lives in `skills/<skillId>/`:

- `skills/<skillId>/manifest.json`
  - `skillId`
  - `version`
  - `bindings` (alias -> server prefix)
  - `fanoutTools` (the raw tools the skill may call)

- `skills/<skillId>/SKILL.md`
  - human-readable purpose
  - interface signatures
  - fanout list

- `skills/<skillId>/lib.py`
  - Python implementation of the skill
  - uses `_bindings` injected from the runtime

Example skills in this repo:
- `skills/docs-to-files/*`
- `skills/repo-insight/*`

---

## Tool Registry (Local Source of Truth)

Tools are represented locally (not via Python RAG) using:

- `tools_schema.json`: machine-readable tool definitions used for retrieval.
- `tools/`: human-readable Markdown + JSON per tool.

This supports a critical constraint: we never need to feed the LLM “the whole world”; we only pass the relevant subset.

---

## Policy Model (JSON + Engine)

GCM uses policy as data, with RBAC and ABAC deliberately separated.

### RBAC (Role → Skill Permissions)

- Stored in `policy/role_permissions.json`
- Loaded by `src/policy/roles.ts`

This maps roles to skill refs (or wildcards):

```json
{
  "mcp:admin": ["*"],
  "mcp:docs-curator": ["skills:docs-to-files@1"]
}
```

RBAC can be updated by admin workflows, but always with human approval.

### ABAC (Rules + Conditions)

- Stored in `policy/policy_rules.json`
- Loaded by `PolicyEngine.loadRulesFromFile()`

ABAC is human-controlled. Agents may propose ABAC changes but do not write them automatically.
Rules can express org/team restrictions via `allowedOrgIds` / `allowedTeamIds`.

---

## The Agents (What Exists Today)

### 1) Runtime Agent (Skill Selection + Code Generation)

- Finds allowed skills based on identity
- Retrieves minimal workflow examples (org-scoped + skill-permission filtered)
- Builds a RICECO prompt (context includes bindings, interfaces, fanout tools, workflows)
- Calls a local LLM endpoint
- Audits the code output and repairs if needed
- Saves successful workflows to `workflows_gcm/<orgId>/...` for reuse

Key implementation:
- `src/agent/agent.ts`
- `src/agent/prompt_builder.ts`
- `src/workflow_registry/*`

Tests:
- `tests/agent_scope.test.ts`
- `tests/agent_e2e_llm.test.ts`
- `tests/gcm_workflow_reuse.test.ts`
- `tests/workflow_registry.test.ts`

### 2) Admin Skill Creator Agent (Create New Skills)

This is a separate agent dedicated to creating new skills (admin-only).

Flow:
- take a user goal
- retrieve a small relevant tool set from `tools_schema.json`
- generate a skill draft via RICECO prompt
- validate draft against tool context
- if tools are missing: expand tool context and retry
- write the skill files into `skills/<skillId>/...`
- update RBAC grants (human-approved)
- emit an ABAC proposal for manual review

Key implementation:
- `src/skill_creator/skill_creator_agent.ts`
- `src/skill_creator/tool_retriever.ts`
- `src/skill_creator/prompt_builder.ts`

Test:
- `tests/skill_creator_e2e.test.ts`

---

## Running GCM

### Start Server Mode

```bash
bun run src/index.ts
```

### Execute a Workflow

```bash
bun run src/index.ts --execute path/to/workflow.py
```

### Create a Skill (Admin)

```bash
bun run src/index.ts --skill-create "Fetch docs and store them" --role mcp:docs-curator --org org_123 --team team_456
```

Notes:
- The skill creator writes into `skills/` and updates RBAC (`policy/role_permissions.json`).
- ABAC proposals are printed for manual approval; agents never write `policy/policy_rules.json`.
- The skill creator expects `LLM_API_BASE` / `LLM_MODEL_NAME` for the local LLM.

---

## Testing

```bash
bun test
```

Key tests to validate the full flow:
- `tests/agent_scope.test.ts` (RBAC + skill selection)
- `tests/agent_e2e_llm.test.ts` (real local LLM + static audit)
- `tests/skill_creator_e2e.test.ts` (skill creation end-to-end)

---

## Current State vs Roadmap

### What’s solid today

- Double-gated security model (static audit + runtime policy)
- Sandbox execution entrypoints
- Local tool registry (`tools_schema.json`)
- Versioned skills with manifests
- A real local-LLM end-to-end test
- Admin skill creator agent with tool expansion loop

### What we’re building next

- **Skills as first-class MCP tools** (e.g., `skills.<skill>.<fn>` routed through the manager)
- **Stronger retrieval**: upgrade TS retriever to vector search later without changing the agent contracts
- **Missions**: budgets, retries, state capture, and richer audit trails
- **Safer user-facing UX**: approvals, diff views, and higher-level policy workflows

---

## Design Principles (Non-Negotiables)

1. Skills first; raw tools are an implementation detail.
2. Retrieval can be fuzzy; execution is deterministic.
3. Version everything; prefer immutability.
4. Sandbox never gets secrets.
5. Two gates always: audit before run, policy during run.

---

## References

- `docs/GOVERNED_CODE_MODE.md`
- `docs/GCM_SKILLS_SUMMARY.md`
- `README.md` (legacy, YAML-era; kept for historical context)
