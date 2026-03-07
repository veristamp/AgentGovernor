# File Patcher Package 🔧

**Safe code mutations with judgment gates.**

## Quick Start

```python
from file_patcher import create_patcher_manager

# Initialize once
patcher = create_patcher_manager(
    qdrant_client=qdrant,
    session_maker=db_session
)

# 1. PATCH - Edit an existing chunk
result = await patcher.patch(
    file_path="src/main.py",
    collection="kb_chunks",
    chunk={"id": 123, "index": 5, "processed_char_start": 100, ...},
    new_content="def fixed_function():\n    return True"
)

# 2. CREATE - Assemble new file from existing chunks
result = await patcher.create(
    grafts=[
        {"source": "src/utils.py", "start": 0, "end": 500},
        {"source": "src/models.py", "start": 100, "end": 300}
    ],
    output_path="generated/hybrid.py"
)

# 3. WRITE - Direct guarded write
success, receipt = await patcher.write(
    file_path="output.py",
    content="print('hello')"
)
```

That's it! **3 methods** for all file mutations.

---

## What Happens Behind the Scenes

| You Call | System Does |
|----------|-------------|
| `patch()` | Acquires lock → Validates syntax → Applies patch → Updates embedding → Ripples offsets |
| `create()` | Loads sources → Assembles grafts → Validates → Writes with guards |
| `write()` | Runs judgment pipeline → Writes if approved |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     HIGH LEVEL - FilePatcherManager                          │
│                                                                              │
│   patch()              create()              write()                         │
│     │                    │                     │                             │
│     └────────────────────┼─────────────────────┘                             │
│                          ▼                                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                     MID LEVEL - Operations                                   │
│                                                                              │
│   ┌──────────────────────┐          ┌──────────────────────┐                │
│   │   SurgicalPatcher    │          │ FrankensteinStitcher │                │
│   │                      │          │                      │                │
│   │ • Byte-precise edit  │          │ • Byte-copy grafts   │                │
│   │ • Distributed lock   │          │ • Glue code support  │                │
│   │ • Vector Ripple      │          │ • Comment headers    │                │
│   └──────────────────────┘          └──────────────────────┘                │
│                                                                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                     LOW LEVEL - Core Primitives                              │
│                                                                              │
│   apply_patch()    assemble()    ripple()    read_file()    write_file()    │
│   PatchDelta       PatchResult                                               │
│                                                                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                     GUARDS - Judgment Pipeline                               │
│                                                                              │
│   ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐            │
│   │  Validate  │  │  Critique  │  │   Impact   │  │   Tests    │            │
│   │  (syntax)  │  │   (diff)   │  │  (oracle)  │  │  (immune)  │            │
│   └────────────┘  └────────────┘  └────────────┘  └────────────┘            │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Key Concepts

### 1. Surgical Edit

Replace a chunk at exact byte offsets while keeping the rest of the file intact.

```python
# Chunk metadata from Qdrant
chunk = {
    "id": 123,
    "index": 5,
    "processed_char_start": 1000,
    "processed_char_end": 1500,
    "original_text": "def old_function():..."
}

result = await patcher.patch(
    file_path="src/main.py",
    collection="kb_chunks",
    chunk=chunk,
    new_content="def new_function():..."
)

print(f"Bytes changed: {result.delta['char']}")
print(f"Downstream updated: {result.downstream_updated}")
```

### 2. Vector Ripple

When you edit a chunk, all chunks AFTER it shift position. Vector Ripple updates their metadata without re-embedding:

```
Before: [Chunk 1][Chunk 2][Chunk 3][Chunk 4]
Edit:   [Chunk 1][LARGER Chunk 2][Chunk 3][Chunk 4]
                            +100 bytes  +100 bytes

Ripple updates Chunk 3 and 4's offsets by +100 bytes
```

### 3. Frankenstein Stitching

Create new files by grafting verified chunks from existing files:

```python
result = await patcher.create(
    grafts=[
        {"source": "src/auth.py", "start": 0, "end": 200},
        {"source": "src/utils.py", "start": 500, "end": 800, "glue": "\n# Adapter\n"},
        {"source": "src/models.py", "start": 100, "end": 400}
    ],
    output_path="generated/combined.py"
)

print(f"Grafts: {result.grafts_count}")
print(f"Bytes: {result.bytes_assembled}")
```

**Philosophy**: "The best code is code that already works."

### 4. Distributed Locking

Prevents concurrent edits to the same file using Postgres CAS locks:

```
Agent A: Acquires lock on src/main.py ✓
Agent B: Tries to lock src/main.py → BLOCKED
Agent A: Finishes edit, releases lock
Agent B: Now can acquire lock ✓
```

---

## Judgment Gates

All writes pass through the judgment pipeline:

| Gate | Purpose | Default |
|------|---------|---------|
| **Validate** | Tree-sitter syntax check | ✅ Enabled |
| **Critique** | Diff discipline (scope, comments) | ❌ Disabled |
| **Impact** | Blast radius analysis | ❌ Disabled |
| **Tests** | Run related tests | ❌ Disabled |

Configure globally:

```python
from file_patcher import PatcherConfig, create_patcher_manager

config = PatcherConfig(
    validate_syntax=True,
    run_critic=True,
    run_impact=False,
    run_tests=False
)

patcher = create_patcher_manager(
    qdrant_client=qdrant,
    session_maker=db,
    **config.__dict__
)
```

---

## Low-Level Access

For fine-grained control:

```python
from file_patcher import SurgicalPatcher, FrankensteinStitcher
from file_patcher.core import apply_patch, assemble, ripple, PatchDelta

# Use core primitives directly
result = apply_patch(
    original="def foo(): pass",
    start=0,
    end=15,
    new_content="def bar(): return True"
)

print(result.patched_content)
print(result.delta.char_delta)
```

---

## File Structure

```
file_patcher/
├── __init__.py        # Clean exports
├── manager.py         # FilePatcherManager (3-method API)
├── surgical.py        # SurgicalPatcher + PatchReceipt
├── stitcher.py        # FrankensteinStitcher + StitchResult
├── core.py            # Low-level primitives
├── guards.py          # Judgment pipeline wrapper
└── README.md          # This file
```

---

## Related Modules

| Module | Purpose |
|--------|---------|
| `judgment/` | Validator, Critic, Oracle, Immune System |
| `latent_memory/` | Memory + Feedback + Prompt Building |
| `rag/` | Retrieval pipeline |
