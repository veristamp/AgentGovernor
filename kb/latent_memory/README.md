# Latent Memory Package 🧠

**Unified AI Memory Interface** - The invisible brain for your LLM.

## Quick Start

```python
from latent_memory import create_memory_manager

# Initialize once
llm = create_memory_manager(
    system_prompt="You are a helpful coding assistant.",
    pg_session=db_session,
    qdrant_client=qdrant
)

# 1. PREPARE - Build prompt with context + history
prompt = await llm.prepare(
    session_id="user_abc",
    query="How does the chunker work?",
    chunks=retrieved_chunks
)

# 2. Call your LLM
response = await openai.chat.completions.create(messages=[...])

# 3. LEARN - Save turn + extract citations
await llm.learn(
    session_id="user_abc",
    query="How does the chunker work?",
    chunks=retrieved_chunks,
    response=response.content
)

# 4. FEEDBACK - When user clicks 👍/👎
await llm.feedback(chunk_ids=[123, 456], positive=True)

# 5. FORGET - Clear a session
await llm.forget(session_id="user_abc")
```

That's it! **4 methods** is all you need.

---

## What Happens Behind the Scenes

| You Call | System Does |
|----------|-------------|
| `prepare()` | Recalls history → Boosts chunks → Fits to token budget → Builds cache-optimal prompt |
| `learn()` | Saves turns → Extracts citations → Updates feedback graph → Triggers compression |
| `feedback()` | Updates Qdrant payloads → Enables Recommend API |
| `forget()` | Clears session → Optionally preserves compressed LTM |

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                    LatentMemoryManager                            │
│                                                                   │
│     prepare()       learn()       feedback()       forget()       │
│         │              │              │               │           │
│         └──────────────┼──────────────┼───────────────┘           │
│                        ▼                                          │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │                   Internal (Hidden)                          │ │
│  │                                                              │ │
│  │  ┌─────────────────┐  ┌───────────────┐  ┌────────────────┐  │ │
│  │  │MemoryOrchestrator│  │ContextRotator │  │KVCacheManager │  │ │
│  │  │  3-tier memory  │  │ Token budget  │  │ Prompt build  │  │ │
│  │  └─────────────────┘  └───────────────┘  └────────────────┘  │ │
│  │                                                              │ │
│  │  ┌──────────────────────────────────────────────────────┐    │ │
│  │  │ FeedbackManager (SoftLoop + HardLoop)               │    │ │
│  │  └──────────────────────────────────────────────────────┘    │ │
│  └──────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────┘
```

---

## Memory Tiers

| Tier | Name | Storage | Retention | Transition |
|------|------|---------|-----------|------------|
| **0** | Working | In-memory | Current request | → Tier 1 after response |
| **1** | Episodic | Postgres | Last K turns (full text) | → Tier 2 when >20 turns |
| **2** | Semantic | Qdrant + Postgres | Compressed summaries | 30 days |

Transitions are **automatic** - zero configuration needed.

---

## Component Responsibilities

| Component | Does | Does NOT |
|-----------|------|----------|
| **MemoryOrchestrator** | What history to recall, compression, LTM | Token limits, prompt format |
| **ContextRotator** | Token budgeting, chunk eviction | History, prompt building |
| **KVCacheManager** | Prompt structure, stable ID ordering | Token limits, memory |
| **FeedbackManager** | Learning from citations/user feedback | Memory, prompts |

---

## Feedback System

Two-tier learning:

| Tier | Signal | Source | Confidence |
|------|--------|--------|------------|
| **Soft** | LLM Citations | Automatic | Lower |
| **Hard** | User 👍/👎 | Explicit | Higher |

Both update the retrieval system to improve future results.

---

## Configuration

Most users don't need to configure anything. For power users:

```python
from latent_memory import LatentConfig, LatentMemoryManager

config = LatentConfig(
    max_tokens=128000,       # Context window size
    reserve_for_output=4000, # Tokens reserved for generation
    history_k=10,            # Recent turns to include
    enable_feedback=True,    # Learn from citations
    enable_compression=True, # LLM summarization
    enable_ltm=True          # Cross-session memory
)

llm = LatentMemoryManager(
    system_prompt="...",
    pg_session=db,
    config=config
)
```

---

## Low-Level Access

For advanced use cases, import internal components directly:

```python
# Memory tiers
from latent_memory.memory import (
    MemoryOrchestrator, EpisodicMemory, SemanticMemory,
    Turn, Memory, MemoryConfig
)

# Token budgeting
from latent_memory import ContextRotator, TokenBudget

# Prompt building
from latent_memory import KVCacheManager

# Feedback
from latent_memory import FeedbackManager, SoftFeedbackLoop, HardFeedbackLoop
```

---

## Background Worker

For automatic compression and cleanup:

```bash
# Run continuously (every 60s)
uv run python -m cli.run_memory_worker

# Run once
uv run python -m cli.run_memory_worker --once

# Custom interval
uv run python -m cli.run_memory_worker --interval 300
```

---

## File Structure

```
latent_memory/
├── __init__.py              # Clean exports
├── manager.py               # LatentMemoryManager (4-method API)
│
├── memory/                  # 3-Tier Memory System
│   ├── orchestrator.py      # Brain - routes to tiers
│   ├── episodic.py          # Tier 1: Recent turns
│   ├── semantic.py          # Tier 2: Compressed LTM
│   ├── compressor.py        # LLM summarization
│   └── models.py            # Turn, Memory, Config
│
├── feedback/                # Learning System
│   ├── manager.py           # Unified facade
│   ├── soft_loop.py         # Citation extraction
│   └── hard_loop.py         # User feedback
│
├── kv_cache.py              # Prompt builder (cache-optimal)
└── context_rotator.py       # Token budget manager
```

---

## Related Modules

| Module | Purpose |
|--------|---------|
| `file_patcher/` | Code mutations with safety gates |
| `judgment/` | Validator, Critic, Oracle, Immune |
| `rag/` | Retrieval pipeline |

---

## Cache Contract

For maximum KV Cache hits, prompts follow this structure:

| Position | Content | Cache Status |
|----------|---------|--------------|
| 1 | System Prompt | ✅ Always cached |
| 2 | Context (sorted by ID) | ✅ Cached until edit |
| 3 | History | ✅ Cached while stable |
| 4 | Query + Metadata | ❌ Recomputed |

**Key**: Sort by stable ID (content hash), not token_start!
