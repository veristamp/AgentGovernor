# Governed Code Mode Architecture

> **Zero-Trust AI Agent Execution with Double-Gated Security**

## Overview

Governed Code Mode is a secure execution architecture where:
- **LLM generates Python code** (SLM-friendly, easy to generate)
- **Code is statically analyzed** before execution (Gate 1)
- **Code runs in NsJail sandbox** with no I/O except Unix socket
- **All MCP calls pass through policy gate** at runtime (Gate 2)
- **Secrets never enter the sandbox**

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  LLM/SLM generates Python code                                              │
│       │                                                                     │
│       ▼                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  GATE 1: Static Auditor (Python)                                    │   │
│  │  • Parse AST                                                        │   │
│  │  • Extract manifest: tools that WILL be called                      │   │
│  │  • Policy check BEFORE execution                                    │   │
│  │  • REJECT if identity lacks required scopes                         │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│       │                                                                     │
│       ▼ (only if Gate 1 passes)                                            │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  NsJail Sandbox (Linux kernel isolation)                            │   │
│  │  • No network (clone_newnet)                                        │   │
│  │  • No filesystem except /mcp.sock + /tmp                            │   │
│  │  • Memory limit (512MB), CPU limit (10s), Wall time (60s)           │   │
│  │  • Seccomp syscall filter                                           │   │
│  │  • Python workflow runs here                                        │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│       │                                                                     │
│       │ JSON-RPC over Unix socket                                          │
│       ▼                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  GATE 2: MCPClientManager (Bun + TypeScript)                        │   │
│  │  • Validate identity (Auth SDK JWT)                                 │   │
│  │  • Check kill switch (real-time revocation)                         │   │
│  │  • Check policy AGAIN (runtime ABAC)                                │   │
│  │  • INJECT secrets (API keys added at edge)                          │   │
│  │  • Execute actual MCP tool call                                     │   │
│  │  • Log to audit trail                                               │   │
│  │  • Return result (secrets stripped)                                 │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│       │                                                                     │
│       ▼                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  MCP Servers (External tools)                                       │   │
│  │  • Cortex (RAG, Patcher, Memory, etc.)                              │   │
│  │  • GitHub, Slack, Filesystem, etc.                                  │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Technology Choices

| Component | Technology | Rationale |
|-----------|-----------|-----------|
| MCPClientManager | Bun + TypeScript | Fast async I/O, type-safe, official MCP SDK |
| Static Auditor | Python | Parses Python AST natively |
| Workflow Code | Python | SLM-friendly, minimal syntax |
| Sandbox | NsJail | Kernel-level isolation, Google-proven |
| Communication | Unix Socket | Streaming, no network exposure |
| Protocol | JSON-RPC 2.0 | Standard, no eval() needed |

---

## Directory Structure

```
mcp-inspector/
├── src/                              # TypeScript (Bun)
│   ├── mcp-client/
│   │   ├── manager.ts               # MCPClientManager
│   │   ├── config.ts                # Config loader
│   │   ├── indices.ts               # Capability index
│   │   └── types.ts                 # TypeScript types
│   ├── socket-server/
│   │   ├── server.ts                # Unix socket server
│   │   └── protocol.ts              # JSON-RPC handler
│   ├── policy/
│   │   ├── engine.ts                # ABAC policy engine
│   │   ├── scopes.ts                # Scope definitions
│   │   └── auth.ts                  # Auth SDK integration
│   ├── audit/
│   │   └── logger.ts                # Audit trail
│   └── index.ts                     # Entry point
├── auditor/                          # Python
│   ├── analyzer.py                  # AST → Manifest
│   └── checker.py                   # Manifest → Allow/Deny
├── sandbox/                          # NsJail config + Python runtime
│   ├── nsjail.cfg                   # NsJail configuration
│   ├── launcher.ts                  # Spawns NsJail from Bun
│   └── runtime/
│       └── mcp.py                   # Minimal MCP client (inside jail)
├── package.json
├── tsconfig.json
└── bunfig.toml
```

---

## Security Model

### Gate 1: Static Auditor (Pre-Execution)

Before any code runs, extract what it WILL do:

```python
# LLM generates:
async def main():
    results = await mcp.use("cortex.search", query=user_input)
    await mcp.use("filesystem.delete", path="/important")
    return results
```

Static Auditor produces manifest:
```json
{
  "tools": ["cortex.search", "filesystem.delete"],
  "static_args": {
    "filesystem.delete": {"path": "/important"}
  }
}
```

Policy check: Does identity have scope `filesystem.delete`? → **REJECT**

### Gate 2: MCPClientManager (Runtime)

Even if code passes Gate 1, every call is checked again:

1. **Identity validation** - JWT verified via Auth SDK
2. **Kill switch check** - Is this identity revoked?
3. **Scope check** - Does identity have this scope?
4. **Resource check** - Can identity access THIS resource?
5. **Secrets injection** - Add API keys at the edge
6. **Audit logging** - Record everything

### Secrets Injection

```
Sandbox sends:  {"method": "slack.post", "params": {"channel": "#general"}}
                              │
                              ▼
MCPClientManager:  Add Authorization header with SLACK_TOKEN
                              │
                              ▼
Slack API:         POST with real credentials
                              │
                              ▼
Sandbox receives:  {"result": {"ok": true}}  ← No token in response
```

---

## Protocol: JSON-RPC over Unix Socket

### Request (Sandbox → Host)
```json
{"jsonrpc": "2.0", "method": "cortex.search", "params": {"query": "auth"}, "id": 1}
```

### Response (Host → Sandbox)
```json
{"jsonrpc": "2.0", "result": [{"file": "auth.py", "score": 0.95}], "id": 1}
```

### Workflow Complete
```json
{"jsonrpc": "2.0", "method": "__complete__", "params": {"result": "Done"}, "id": 99}
```

### Error
```json
{"jsonrpc": "2.0", "error": {"code": -32600, "message": "Unauthorized"}, "id": 1}
```

---

## What SLM Generates

```python
import mcp

async def main():
    # Search for files
    files = await mcp.use("cortex.search", query="authentication bug")
    
    # Read each file
    for f in files:
        content = await mcp.use("cortex.read", path=f["path"])
        if "vulnerability" in content:
            await mcp.use("human.notify", message=f"Found issue in {f['path']}")
    
    return {"checked": len(files)}
```

Simple. No types. No complex imports. SLM-friendly.

---

## Attack Mitigation

| Attack | Mitigation |
|--------|------------|
| Prompt injection → dangerous code | Gate 1 rejects unauthorized tools |
| Jail escape | NsJail kernel isolation (namespaces, seccomp) |
| API key theft | Keys never enter sandbox |
| Unauthorized tool call | Gate 2 runtime policy check |
| Resource exhaustion | NsJail cgroups (memory, CPU) |
| Long-running attack | NsJail wall-clock timeout |
| Audit evasion | All calls logged at Gate 2 |

---

## Implementation Status

### Phase 1: MCPClientManager in TypeScript ✅ COMPLETE
- [x] Project setup (Bun + TypeScript)
- [x] Config loader (`src/mcp-client/config.ts`)
- [x] MCP connection (stdio - http/sse pending)
- [x] Capability indexing (`src/mcp-client/indices.ts`)
- [x] Basic execute_action with policy integration

### Phase 2: Unix Socket Server ✅ COMPLETE
- [x] Socket server setup (`src/socket-server/server.ts`)
- [x] JSON-RPC protocol handler (`src/socket-server/protocol.ts`)
- [x] Request routing to MCPClientManager

### Phase 3: Policy Engine ✅ COMPLETE
- [x] ABAC policy engine (`src/policy/engine.ts`)
- [x] Policy types and conditions (`src/policy/types.ts`)
- [x] Auth SDK integration with JWT validation (`src/policy/auth.ts`)
- [x] Kill switch checking with cache
- [x] Rate limiting

### Phase 4: Static Auditor ✅ COMPLETE
- [x] Python AST parser (`auditor/analyzer.py`)
- [x] Manifest extraction (tools, args, loops, conditionals)
- [x] Pre-execution policy check
- [x] TypeScript bridge (`src/audit/bridge.ts`)

### Phase 5: NsJail Integration ✅ COMPLETE
- [x] NsJail config (`sandbox/nsjail.cfg`)
- [x] Python runtime (`sandbox/runtime/mcp.py`)
- [x] Workflow runner (`sandbox/runtime/runner.py`)
- [x] Launcher from Bun (`sandbox/launcher.ts`)

### Phase 6: Audit Trail ✅ COMPLETE
- [x] Structured logging (`src/audit/logger.ts`)
- [x] Memory storage with limits
- [x] File logging (JSON lines)
- [ ] Postgres persistence (optional, future)

---

## Usage

```bash
# Start in server mode
bun run src/cli/index.ts

# Execute a workflow
bun run src/cli/index.ts --execute examples/test_workflow.py

# Analyze a workflow (static auditor only)
python auditor/analyzer.py examples/test_workflow.py

# Analyze with policy check
python auditor/analyzer.py examples/test_workflow.py --allowed cortex.search cortex.read
```

