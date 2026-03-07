# 🔧 Services Layer

Business logic façade that wraps core Managers with consistent formatting and error handling.

## Philosophy

**"Orchestrate and Format"** - Services should:
- ✅ Wrap underlying managers
- ✅ Format responses consistently
- ✅ Handle errors gracefully
- ✅ Log operations
- ❌ NOT contain core algorithms
- ❌ NOT duplicate manager logic
- ❌ NOT be tightly coupled to HTTP

## Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│                            Services Layer                                 │
│                                                                           │
│  ┌─────────────────────────────────────────────────────────────────────┐ │
│  │  Services (This Layer)                                               │ │
│  │                                                                      │ │
│  │  ChatService          - Chat orchestration, OpenAI-compatible output │ │
│  │  IngestionService     - File/directory ingestion control             │ │
│  │  PatchService         - Surgical patcher operations                  │ │
│  │  GraphService         - Knowledge graph queries                      │ │
│  │  WatcherService       - File watcher lifecycle                       │ │
│  │  PRService            - GitHub/GitLab PR review automation           │ │
│  │                                                                      │ │
│  │  chat/                                                               │ │
│  │  ├── service.py       - ChatService implementation                  │ │
│  │  ├── models.py        - Shared models (Persona, Session, Config)    │ │
│  │  ├── persona_service.py - Persona CRUD                              │ │
│  │  ├── session_service.py - Session management                        │ │
│  │  └── response_formatter.py - OpenAI-compatible formatter            │ │
│  │                                                                      │ │
│  │  pr_scanner/                                                         │ │
│  │  ├── scanner.py       - PRScanner (core logic)                      │ │
│  │  ├── service.py       - PRService (GitHub integration)              │ │
│  │  ├── formatter.py     - PR comment formatter                        │ │
│  │  └── providers/       - GitHub, GitLab API integrations             │ │
│  └─────────────────────────────────────────────────────────────────────┘ │
│                                    │                                      │
│                                    ▼                                      │
│  ┌─────────────────────────────────────────────────────────────────────┐ │
│  │                          Managers Layer                              │ │
│  │                                                                      │ │
│  │  llm/LLMManager       - 4-step orchestration (Retrieve→Prepare→     │ │
│  │                         Generate→Learn)                              │ │
│  │  rag/RAGManager       - Retrieval + reranking + compression         │ │
│  │  latent_memory/       - 3-tier memory (Working→Episodic→Semantic)   │ │
│  │    LatentMemoryManager                                               │ │
│  │  ingestion/           - Scanner + Worker (queue-based)              │ │
│  │    IngestionManager                                                  │ │
│  │  file_patcher/        - VFS staging + surgical edits                │ │
│  │    FilePatcherManager                                                │ │
│  │  judgment/            - Safety gates (Validator, Oracle, Immune)    │ │
│  │    JudgmentManager                                                   │ │
│  └─────────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────┘
```

## Directory Structure

```
services/
├── __init__.py              # Exports
├── README.md                # This file
│
├── chat/                    # Chat domain (complex, multi-file)
│   ├── __init__.py          # Exports ChatService, models
│   ├── service.py           # ChatService - main orchestration
│   ├── models.py            # Persona, Session, Config models
│   ├── persona_service.py   # Persona CRUD
│   ├── session_service.py   # Session management
│   └── response_formatter.py # OpenAI-compatible formatting
│
├── pr_scanner/              # PR review automation (multi-file)
│   ├── __init__.py          # Exports PRService, PRScanner, etc.
│   ├── core.py              # Data structures (PRVerdict, FileChange)
│   ├── diff_parser.py       # Git diff parsing
│   ├── scanner.py           # PRScanner - core logic
│   ├── service.py           # PRService - GitHub/GitLab integration
│   ├── formatter.py         # PR comment Markdown formatting
│   └── providers/           # Git hosting integrations
│       ├── base.py          # Abstract GitProvider
│       └── github.py        # GitHub API implementation
│
├── ingestion_service.py     # IngestionService
├── graph_service.py         # GraphService  
├── patch_service.py         # PatchService
└── watcher_service.py       # WatcherService
```

## Manager vs Service: What's the Difference?

| Aspect | Manager | Service |
|--------|---------|---------|
| **Location** | Module folder (`llm/`, `rag/`) | `services/` folder |
| **Purpose** | Core business logic | Orchestration + formatting |
| **Users** | Services, CLI, tests | API layer, CLI |
| **Response Format** | Raw data, objects | Standardized dicts, OpenAI format |
| **Error Handling** | Raises exceptions | Returns error responses |
| **Reusability** | Maximum | HTTP-focused |

### Example Flow

```
API Request
    │
    ▼
ChatService.chat()          ← Service: orchestrates
    │
    ├─► PersonaService      ← Service: resolves config
    │
    └─► LLMManager.chat()   ← Manager: core logic
            │
            ├─► RAGManager.retrieve()   ← Manager: retrieval
            ├─► LatentMemoryManager.prepare()  ← Manager: memory
            ├─► LLMClient.generate()    ← Core: LLM call
            └─► LatentMemoryManager.learn()    ← Manager: learning
```

## Services Overview

### ChatService
```python
from services import ChatService

service = ChatService(pg_session=session)
response = await service.chat(
    session_id="user_123",
    query="Explain chunking",
    persona="code_assistant"
)
# Returns OpenAI-compatible response
```

### IngestionService
```python
from services import IngestionService

service = IngestionService()
result = await service.ingest_directory(Path("doc/"))
# Returns IngestionResponse with stats
```

### PatchService
```python
from services import PatchService

service = PatchService()
result = await service.apply_patch(file_path, changes)
# Returns patch result with rollback info
```

### GraphService
```python
from services import GraphService

service = GraphService(qdrant_client=qdrant)
summary = await service.get_summary()
# Returns graph statistics
```

### WatcherService
```python
from services import WatcherService

service = WatcherService()
await service.start_watching([Path("doc/")])
# Starts background file watcher
```

### PRService (PR Review Automation)
```python
from services import PRService, create_pr_service

# Quick setup with GitHub token
service = create_pr_service(github_token="ghp_...")

# Scan and post comment to GitHub PR
report = await service.scan_and_comment("owner/repo", pr_number=42)

# Just scan without posting
report = await service.scan_pr("owner/repo", 42)
print(report.summary)  # ✅ APPROVE: 5/5 files passed (low risk)
```

### PRScanner (Local Diff Scanning)
```python
from services import PRScanner, create_pr_scanner

scanner = create_pr_scanner(project_root="f:/kb")

# Scan a local diff
report = await scanner.scan_diff(
    diff_text=git_diff_output,
    pr_number=123,
    repo="myorg/myrepo"
)

# Access results
for file_result in report.file_results:
    print(f"{file_result.file_path}: {file_result.approved}")
```

## Writing a New Service

```python
# services/example_service.py
from typing import Dict, Any, Optional
from config import get_logger

logger = get_logger("ExampleService")

class ExampleService:
    """
    Service description.
    
    Wraps ExampleManager and provides:
    - Consistent response formatting
    - Error handling
    - Logging
    """
    
    def __init__(self, pg_session=None, **kwargs):
        self._pg_session = pg_session
        self._manager = None  # Lazy-loaded
        
    def _get_manager(self):
        """Lazy-load the underlying manager."""
        if self._manager is None:
            from example_module import ExampleManager
            self._manager = ExampleManager(pg_session=self._pg_session)
        return self._manager
    
    async def do_something(self, param: str) -> Dict[str, Any]:
        """
        Do something.
        
        Args:
            param: Description
            
        Returns:
            Standardized response dict
        """
        logger.info(f"📦 Processing: {param}")
        
        try:
            manager = self._get_manager()
            result = await manager.process(param)
            
            return {
                "success": True,
                "data": result,
                "error": None
            }
        except Exception as e:
            logger.error(f"❌ Failed: {e}")
            return {
                "success": False,
                "data": None,
                "error": str(e)
            }
```

## Rules

1. **Wrap, don't duplicate** - Services call managers; they don't reimplement logic
2. **Standardize responses** - Consistent dict structure or Pydantic models
3. **Lazy-load managers** - Only initialize when first used
4. **Log with emojis** - Makes logs scannable (📦 start, ✅ success, ❌ error)
5. **Handle all exceptions** - Services should never raise to API layer
6. **Be stateless when possible** - Easier to test and scale
