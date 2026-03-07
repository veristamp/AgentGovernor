# Skill Creator Agent: Findings + Plan

This document captures the design direction for a "perfect Skill Creator Agent" that iteratively discovers, builds, validates, and learns from outcomes while keeping tools/skills/workflows as first-class citizens of the Knowledge Graph.

## Core Findings

### 1) Source of Truth Must Be the Knowledge Graph

Authoritative:
- Postgres: relational truth for tools/skills/workflows, versions, dependencies, policies, outcomes.
- Qdrant: latent truth for semantic retrieval over descriptions, traces, and "what worked before".

Non-authoritative:
- Local `tools/` folder and any aggregated artifacts like `tools_schema.json`.
- These can exist as a developer cache/build artifact, but must never be treated as truth during skill creation.

### 2) Skill Creation Should Be a Small, Iterative Loop

Avoid:
- single-shot "huge context" prompts
- reading every tool schema upfront
- treating build and discovery as separate worlds

Prefer:
- looped steps with a small working set
- registry queries that fetch only what is needed
- continuous validation gates inside the loop

### 3) Validation Must Happen During the Build, Not Only at the End

Gate 1 already exists: `auditor/skill_analyzer.py`
- Rejects raw IO / network / process access outside bindings.
- Must run after each meaningful edit iteration.

The loop must treat a gate failure as a first-class event that triggers:
- automatic repair
- re-validation
- trace logging for future retrieval

## Design Principles

### A) Determinism Without Local Trust

"Deterministic" here means:
- skills are built against explicit tool identifiers + versions from the registry
- the exact schemas used for codegen can be re-fetched from Postgres

"No local trust" means:
- agent never uses `tools/` as the canonical schema source
- if local caches exist, they are treated as hints only

### B) Tools / Skills / Workflows / Missions Are Graph Nodes

First-class objects should have:
- stable IDs
- versions
- dependencies
- outcomes
- links to traces (success/failure)

This enables:
- iterative retrieval (RAG) over prior successful runs
- dependency reasoning ("skill X requires tool Y")
- process mining / analytics later

### C) Learn Over Time via Traces

Every build/run should emit a trace record that includes:
- intent (what we tried to do)
- selected tools + versions
- gate results (pass/fail + reasons)
- outcome (success/failure)
- minimal diffs/metrics (not full code dumps unless needed)

Embed the WHY (reasoning summary) into Qdrant so retrieval improves over time.

## Proposed Loop (Minimal + Effective)

### Step 0: Registry-First Tooling

To avoid local truth, the agent needs a registry interface that is reachable as tools (MCP) or internal APIs.

Minimum operations:
- `registry.search_tools(query, policy_profile, limit)`
- `registry.get_tool_schema(qualified_name_or_id, version)`
- `registry.search_skills(query, limit)`
- `registry.get_skill(skill_id)`
- `traces.write(trace_payload)` (Postgres) + `traces.embed(trace_payload)` (Qdrant)

Optional but useful:
- `registry.resolve_latest(qualified_name)`
- `registry.list_dependencies(skill_id)`

### Step 1: Discover (Graph, Not Files)

Inputs:
- skill goal
- policy profile (what bindings and tool categories are permitted)
- constraints (dry-run required, hash guards required, etc.)

Actions:
1) Query Postgres tool registry for relevant tools (exact/prefix filtered).
2) Query Qdrant traces for similar tasks and known pitfalls.
3) Fetch full schemas for only the shortlisted tools from Postgres.

Output artifact ("Skill Plan"):
- selected tools (qualified + version)
- algorithm sketch
- required safety constraints (dry-run defaults, sha guards, staging rules)
- risk notes from traces ("this failed before because...")

### Step 2: Build (Small Patches)

Actions:
- write the skill incrementally
- avoid dumping full schemas or huge context; fetch specifics when needed
- after each meaningful change:
  - run Gate 1 (`auditor/skill_analyzer.py`)
  - if fail: repair and repeat

Constraints:
- skills call bindings only (no raw `open`, no `os.system`, etc.)
- the chosen tools/versions are referenced explicitly in metadata

### Step 3: Validate (Beyond Gate 1)

Add lightweight checks around Gate 1:
- Gate 0: syntax parse / import-only smoke checks
- Gate 1: static audit (already exists)
- Optional Gate 2: runtime dry-run checks where supported

The loop should only progress when the current build passes required gates.

### Step 4: Commit + Learn (Graph Updates)

On completion (success or failure), write trace(s):
- intent + reasoning summary
- selected tools and versions
- gate outcomes
- outcome status
- minimal metrics (e.g., files touched, diff size, time, error signatures)

Store:
- Postgres: trace row + tool/skill dependency links
- Qdrant: embedding of reasoning + failure signatures for retrieval

## Suggested Simplifications (Avoid Over-Engineering)

1) Allow discovery during build, but only through registry queries.
2) Keep the working set small: retrieve top-k tools + top-k traces per loop turn.
3) Make gate failures first-class: they are learning signals.
4) Keep local artifacts as developer convenience only; never trust them as truth.

## Next Concrete Actions

1) Define the registry contract (tool names + schemas) that the Skill Creator Agent will call.
2) Ensure the agent can:
   - search tools via Postgres
   - retrieve traces via Qdrant
   - fetch a tool schema by ID/version
3) Wire build-loop validation:
   - run `auditor/skill_analyzer.py` after each patch iteration
   - on failure: repair and rerun
4) Add trace writes for every loop iteration (pass/fail) so retrieval improves.
