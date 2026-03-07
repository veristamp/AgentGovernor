# Latent Memory Architecture 🧠

## Philosophy

**"The best memory is invisible."**

Users shouldn't think about tokens, caching, or eviction. They just:
1. `prepare()` - Get a prompt
2. `learn()` - Save the turn
3. Done.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      LatentMemoryManager                                 │
│                                                                          │
│   prepare()         learn()         feedback()         forget()          │
│       │                │                │                 │              │
│       └────────────────┼────────────────┼─────────────────┘              │
│                        ▼                                                 │
│  ┌───────────────────────────────────────────────────────────────────┐   │
│  │                    Internal Components                            │   │
│  │                                                                   │   │
│  │  ┌─────────────────┐  ┌───────────────┐  ┌─────────────────────┐  │   │
│  │  │MemoryOrchestrator│  │ContextRotator │  │  KVCacheManager   │  │   │
│  │  │                 │  │               │  │                   │  │   │
│  │  │ "What to        │  │ "How much     │  │ "How to order     │  │   │
│  │  │  remember?"     │  │  fits?"       │  │  for cache?"      │  │   │
│  │  │                 │  │               │  │                   │  │   │
│  │  │ 3-Tier Memory   │  │ Token Budget  │  │ Stable ID Sort    │  │   │
│  │  │ Importance      │  │ Chunk Evict   │  │ Prefix Stability  │  │   │
│  │  │ Compression     │  │               │  │                   │  │   │
│  │  └─────────────────┘  └───────────────┘  └─────────────────────┘  │   │
│  │                                                                   │   │
│  │  ┌───────────────────────────────────────────────────────────┐    │   │
│  │  │                    FeedbackManager                        │    │   │
│  │  │  SoftFeedbackLoop (citations) + HardFeedbackLoop (👍/👎)  │    │   │
│  │  └───────────────────────────────────────────────────────────┘    │   │
│  └───────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Component Responsibilities

### Single Responsibility Principle

| Component | Responsibility | Does NOT Handle |
|-----------|----------------|-----------------|
| **MemoryOrchestrator** | What history to recall, compression, LTM | Token limits, prompt format |
| **ContextRotator** | Token budgeting, chunk eviction | History, prompt building |
| **KVCacheManager** | Prompt structure, stable ID ordering | Token limits, memory |
| **FeedbackManager** | Learning from citations/user feedback | Memory, prompts |

---

## The Flow

```
1. prepare(session_id, query, chunks)
   │
   ├──▶ MemoryOrchestrator.recall()
   │    └── Returns relevant history (episodic + LTM)
   │
   ├──▶ FeedbackManager.boost_results()
   │    └── Re-ranks chunks based on learned signals
   │
   ├──▶ ContextRotator.fit_chunks()
   │    └── Evicts low-score chunks if over budget
   │
   └──▶ KVCacheManager.build()
        └── Assembles prompt in cache-optimal order
        
2. LLM generates response

3. learn(session_id, query, chunks, response)
   │
   ├──▶ MemoryOrchestrator.remember()
   │    └── Saves turn to episodic memory
   │
   └──▶ FeedbackManager.process_turn()
        └── Extracts citations, updates signals
```

---

## The Cache Contract 📜

To maximize KV Cache hits, prompts must follow this structure:

| Position | Content | Variability | Cache Status |
|----------|---------|-------------|--------------|
| 1 | System Prompt | **Static** | ✅ Always cached |
| 2 | Context Chunks | **Stable** (sorted by ID) | ✅ Cached until edit |
| 3 | History | **Episodic** | ✅ Cached while stable |
| 4 | Query + Metadata | **Dynamic** | ❌ Recomputed |

**Key Insight**: Sort by stable ID (content hash), NOT token_start. IDs don't change on file edit!

---

## Memory Tiers

```
┌─────────────────────────────────────────────────────────────────┐
│                    MemoryOrchestrator                            │
│                                                                  │
│  ┌─────────────┐      ┌─────────────┐      ┌─────────────┐      │
│  │   WORKING   │ ───▶ │  EPISODIC   │ ───▶ │  SEMANTIC   │      │
│  │   Tier 0    │      │   Tier 1    │      │   Tier 2    │      │
│  │             │      │             │      │             │      │
│  │ Current     │      │ Last K      │      │ Compressed  │      │
│  │ turn only   │      │ turns       │      │ summaries   │      │
│  │ In-memory   │      │ Postgres    │      │ Qdrant+PG   │      │
│  └─────────────┘      └─────────────┘      └─────────────┘      │
│                                                                  │
│  Automatic promotion: Working → Episodic (after response)       │
│  Automatic compression: Episodic → Semantic (when >20 turns)    │
└─────────────────────────────────────────────────────────────────┘
```

---

## Token Budget Management

```python
# ContextRotator handles the math
rotator = ContextRotator(
    max_tokens=128000,      # Context window
    reserve_for_output=4000  # Leave room for generation
)

# Input: All retrieved chunks
# Output: Only chunks that fit, sorted by score
fitted, budget = rotator.fit_chunks(
    chunks=retrieved_chunks,
    history_tokens=500,
    query_tokens=100
)

# budget.to_dict() shows:
# {
#   "max_tokens": 128000,
#   "chunk_tokens": 50000,
#   "history_tokens": 500,
#   "available": 73400,
#   "utilization": "42.6%"
# }
```

---

## Feedback Learning

Two-tier system:

| Tier | Signal Type | Source | Action |
|------|-------------|--------|--------|
| **Soft** | LLM cites chunk | Automatic | Boost chunk for similar queries |
| **Hard** | User 👍/👎 | Explicit | Update Qdrant payload, enable Recommend |

```python
# Soft: Happens automatically in learn()
# If LLM says "[cite:123]", chunk 123 gets boosted

# Hard: When user clicks 👍
await manager.feedback(chunk_ids=[123, 456], positive=True)
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
├── context_rotator.py       # Token budget manager
└── history.py               # Basic history (deprecated by memory/)
```

---

## Usage Summary

```python
from latent_memory import create_memory_manager

# Initialize once
llm = create_memory_manager(
    system_prompt="You are a helpful assistant.",
    pg_session=db,
    qdrant_client=qdrant
)

# Every turn:
prompt = await llm.prepare(session_id, query, chunks)
response = await call_llm(prompt)
await llm.learn(session_id, query, chunks, response)

# Optional: User feedback
await llm.feedback(chunk_ids, positive=True)

# Clear session
await llm.forget(session_id)
```

**That's it. 4 methods for everything.**
