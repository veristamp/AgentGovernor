# 🧠 LLM Orchestration & Layer Cake Memory

The `llm` package is the **"Split-Brain" Controller**. It orchestrates the flow between Retrieval-Augmented Generation (RAG), Short-Term Memory (STM), and various LLM providers using a unified **Manager Pattern**.

## 🎛️ User Control API

The LLM system now provides **full user control** over all features via API parameters:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `session_id` | `str?` | `None` | Session ID. `None` = ephemeral (no DB state) |
| `branch_from` | `str?` | `None` | Fork conversation from another session |
| `include_history` | `bool` | `True` | Load conversation history from DB |
| `history_k` | `int` | `10` | Number of history turns to include |
| `learn` | `bool` | `True` | Save this turn to memory |
| `include_ltm` | `bool` | `True` | Include long-term semantic memories |
| `use_rag` | `bool` | `True` | Enable RAG retrieval |
| `retrieval_limit` | `int` | `5` | Number of chunks to retrieve |

### Example: Full Control

```python
# Ephemeral chat (no session tracking)
response = await llm.chat(
    session_id=None,  # No persistence
    query="What is RAG?"
)

# Persistent session with full history
response = await llm.chat(
    session_id="user_123_conv_1",
    query="Explain chunking",
    include_history=True,
    history_k=10,
    learn=True
)

# Branch a conversation for exploration
response = await llm.chat(
    session_id="user_123_conv_1_alt",
    branch_from="user_123_conv_1",  # Copy history from here
    query="Actually, try a different approach"
)

# Pure LLM mode (no RAG, no memory)
response = await llm.chat(
    session_id=None,
    query="Write a haiku",
    use_rag=False,
    include_history=False
)
```

---

## 🏗️ Architecture

### The 4-Step Orchestration Cycle

The `LLMManager` follows a strict cycle for every turn:

1. **RETRIEVE**: Semantic search via `RAGManager` (if `use_rag=True`)
2. **PREPARE**: Build cache-optimal prompt with history via `LatentMemoryManager`
3. **GENERATE**: Multi-provider execution (OpenAI, Anthropic, Ollama, etc.)
4. **LEARN**: Save turn and extract feedback (if `learn=True`)

### The "Layer Cake" Prompt Strategy 🍰

To maximize **Prompt Cache** efficiency, prompts are assembled in deterministic order:

| Layer | Type | Description | Stability |
| :--- | :--- | :--- | :--- |
| **System** | `[STATIC]` | "You are a helpful assistant..." | **Permanent** |
| **Graph Context** | `[STABLE]` | Chunks sorted by **Stable ID** (not relevance) | **High** |
| **History** | `[EPISODIC]` | Last K turns of conversation | **Medium** |
| **User Query** | `[DYNAMIC]` | The new input (placed at the very end) | **None** |

> ⚠️ **STABILITY RULE**: Chunks are sorted by their `id` (content hash), NOT by Relevance Score. Scores fluctuate; hashes are forever. This ensures the prefix remains byte-for-byte identical across turns.

---

## 📂 Module Structure

- **`manager.py`**: The central `LLMManager`. Orchestrates the 4-step cycle.
- **`client.py`**: The `LLMClient` facade. Unified interface for 12+ providers.
- **`kernel.py`**: Shared infrastructure (Base classes, Retry logic, Env utils).
- **`cache_adapter.py`**: Provider-specific cache hints (OpenAI, Anthropic, Gemini, Groq).
- **`providers/`**: Optimized implementations for each provider.

---

## 🚀 Usage

### Basic Initialization

```python
from llm import create_llm_manager

llm = create_llm_manager(
    provider="openai",
    model="gpt-4o-mini",
    pg_session=db_session
)

# Execute the chat cycle with user control
response = await llm.chat(
    session_id="session_01",
    query="How does the Surgical Patcher work?",
    use_rag=True,
    include_history=True,
    history_k=10
)

print(response["response"])
print(f"Latency: {response['latency_ms']}ms")
print(f"Config used: {response['config_used']}")
```

### Multi-Provider Flexibility

```python
# Use local Ollama
llm = create_llm_manager(provider="ollama", model="qwen2.5:14b")

# Use ultra-fast Groq
llm = create_llm_manager(provider="groq", model="llama-3.3-70b-versatile")
```

---

## 📊 Response Metadata

Every response includes detailed metadata:

```python
{
    "response": "The Surgical Patcher is...",
    "session_id": "session_01",
    "chunk_ids": [123, 456, 789],
    "chunks": [...],
    "latency_ms": 1234,
    "config_used": {  # What was actually applied
        "use_rag": True,
        "retrieval_limit": 5,
        "include_history": True,
        "history_k": 10,
        "include_ltm": True,
        "learned": True
    },
    # Token/cache metadata
    "cached": True,
    "cached_tokens": 12400,
    "input_tokens": 12800,
    "output_tokens": 256
}
```

---

## 📈 Monitoring & Performance

The manager monitors **Prompt Caching** hits automatically:

- **Cache HIT**: `🚀 Prompt Cache HIT: 12400/12800 tokens cached (96.8%)`
- **Cache MISS**: `📦 Prompt Cache MISS: (First turn on this topic)`

Logs also show what features were used:
- `💬 Chat: RAG: 5 chunks, history: 10t, 1234ms, cached=True`

