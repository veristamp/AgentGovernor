# Judgment System 🔍

**"Senior Engineer in a Box"** - Automated safety gates for code modifications.

## Quick Start

```python
from judgment import create_judgment_manager

# Initialize once
judgment = create_judgment_manager(
    session_maker=db_session,
    project_root="f:/kb"
)

# Evaluate a patch
result = await judgment.evaluate_patch(
    file_path="src/main.py",
    old_content="def foo(): pass",
    new_content="def foo(): return True"
)

if result.approved:
    print("✅ Patch approved!")
    # Apply the patch...
else:
    print(f"❌ Rejected by: {result.rejected_by}")
    for error in result.errors:
        print(f"  - {error}")
```

---

## The 5 Gates

| Gate | Purpose | Speed | Default |
|------|---------|-------|---------|
| **Validator** | Syntax checking (tree-sitter) | Fast | ✅ On |
| **Linter** | Duplicate detection | Fast | ✅ On |
| **Critic** | Diff discipline | Fast | ❌ Off |
| **Oracle** | Impact analysis (blast radius) | Medium | ❌ Off |
| **Immune** | Test verification | Slow | ❌ Off |

Gates run **in parallel** (except Immune) for maximum speed.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     HIGH LEVEL - JudgmentManager                             │
│                                                                              │
│   evaluate_patch(file, old, new)                                            │
│       │                                                                      │
│       ├──▶ Parallel: Validator | Linter | Critic | Oracle                   │
│       │                                                                      │
│       └──▶ Sequential: Immune (if enabled)                                  │
│                                                                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                     MID LEVEL - Individual Gates                             │
│                                                                              │
│   ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐           │
│   │  Validator  │ │   Linter    │ │   Critic    │ │   Oracle    │           │
│   │             │ │             │ │             │ │             │           │
│   │ tree-sitter │ │  semantic   │ │  diff rules │ │  ripgrep    │           │
│   │ AST parse   │ │  similarity │ │  violations │ │  callers    │           │
│   └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘           │
│                                                                              │
│   ┌─────────────────────────────────────────────────────────────┐           │
│   │                        Immune                                │           │
│   │   Run pytest → Parse results → Pass/Fail decision           │           │
│   └─────────────────────────────────────────────────────────────┘           │
│                                                                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                     LOW LEVEL - Core                                         │
│                                                                              │
│   GateType | Decision | RiskLevel | Severity                                │
│   JudgmentResult | JudgmentConfig                                           │
│                                                                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                     AUDIT - VPC (Patch Logger)                               │
│                                                                              │
│   PatchRecord | PatchDecision | RejectionGate                               │
│   Postgres persistence for complete audit trail                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Gate Details

### 1. Validator (Syntax)

Uses **tree-sitter** to parse code and detect syntax errors BEFORE writing to disk.

```python
from judgment import PatchValidator, create_validator

validator = create_validator(strict_mode=True)

# Validate code directly
result = validator.validate_syntax("def foo():", "python")
print(result.valid)  # False - missing body

# Validate patch preview
preview = validator.validate_patch_preview(
    file_path="src/main.py",
    chunk_metadata={"processed_char_start": 0, "processed_char_end": 50},
    new_content="def bar(): return True"
)
```

**Supported Languages**: Python, JavaScript, TypeScript, Go, Rust, Java, C/C++, Ruby, Bash

### 2. Linter (Duplicates)

Detects **semantic duplication** - code that's similar to existing chunks.

```python
from judgment import SemanticLinter, create_linter

linter = create_linter(qdrant_client=qdrant)

duplicates = await linter.analyze_text(
    text="def calculate_sum(a, b): return a + b",
    filename="utils.py",
    threshold=0.85
)

for dup in duplicates:
    print(f"Similar to: {dup['matches'][0]['source']}")
```

### 3. Critic (Diff Discipline)

Enforces "senior engineer" patch discipline:

| Rule | Description |
|------|-------------|
| **Size** | Changes proportional to intent |
| **Scope** | Don't touch unrelated code |
| **Whitespace** | No formatting drift |
| **Dependencies** | Flag new/removed imports |
| **Safety** | Flag removed error handling/logging |

```python
from judgment import DiffCritic, create_critic

critic = create_critic()

critique = critic.critique_patch(
    old_content="def foo(): pass",
    new_content="def foo(): return True"
)

print(f"Approved: {critique.approved}")
print(f"Score: {critique.score}")
for v in critique.violations:
    print(f"  [{v.severity.value}] {v.message}")
```

### 4. Oracle (Impact Analysis)

Answers: **"What will break if I change this?"**

```python
from judgment import ImpactOracle, create_oracle

oracle = create_oracle(project_root="f:/kb")

report = await oracle.analyze_impact_async(
    file_path="src/utils.py",
    old_content="def helper(): pass",
    new_content="def helper(): return None"
)

print(f"Risk: {report.risk_level.value}")
print(f"Callers: {report.caller_count}")
print(f"Test files: {report.tests.test_files}")
```

Uses **ripgrep** for fast codebase-wide search.

### 5. Immune (Test Verification)

The final gate: **"Do the tests pass?"**

```python
from judgment import ImmuneSystem, create_immune_system

immune = create_immune_system(
    project_root="f:/kb",
    timeout_seconds=60,
    pytest_cmd="uv run pytest"
)

verification = immune.verify_patch(
    file_path="src/utils.py",
    changed_symbols=["helper", "calculate"],
    test_files=["tests/test_utils.py"]
)

print(f"Should apply: {verification.should_apply}")
print(f"Reason: {verification.reason}")
```

---

## Configuration

```python
from judgment import JudgmentConfig, create_judgment_manager

config = JudgmentConfig(
    validate_syntax=True,    # Gate 1
    check_duplicates=True,   # Gate 1b
    run_critic=True,         # Gate 2
    run_impact=True,         # Gate 3
    run_tests=False,         # Gate 4 (expensive)
    strict_mode=True,        # Reject any syntax error
    project_root="f:/kb"
)

judgment = create_judgment_manager(
    session_maker=db,
    **config.__dict__
)
```

---

## VPC (Audit Trail)

Every patch evaluation is logged:

```python
from judgment import PatchLogger, create_patch_logger

logger = create_patch_logger(session_maker=db)

record = await logger.log_patch(
    file_path="src/main.py",
    chunk_metadata={...},
    old_content="...",
    new_content="...",
    receipt={...}
)

print(f"Patch ID: {record.id}")
print(f"Decision: {record.decision}")
```

---

## File Structure

```
judgment/
├── __init__.py        # Clean exports
├── core.py            # Data structures (GateType, Decision, etc.)
├── manager.py         # JudgmentManager (orchestration)
│
├── validator.py       # Gate 1: Syntax (tree-sitter)
├── linter.py          # Gate 1b: Duplicates (semantic)
├── critic.py          # Gate 2: Diff discipline
├── oracle.py          # Gate 3: Impact (ripgrep)
├── immune.py          # Gate 4: Tests (pytest)
│
├── vpc.py             # Audit logging
└── README.md          # This file
```

---

## Integration with File Patcher

The judgment system is automatically used by `file_patcher`:

```python
from file_patcher import create_patcher_manager

patcher = create_patcher_manager(
    qdrant_client=qdrant,
    session_maker=db,
    validate_syntax=True,  # Uses PatchValidator
    run_critic=True,       # Uses DiffCritic
    run_impact=True,       # Uses ImpactOracle
    run_tests=False        # Uses ImmuneSystem
)

# All patches go through judgment automatically
result = await patcher.patch(file, collection, chunk, new_content)
```

---

## Philosophy

> "The best bug is the one that never ships."

The judgment system acts as a **pre-commit hook on steroids**:
- Catches syntax errors before they hit disk
- Enforces code quality at the patch level
- Measures blast radius before changes are made
- Runs tests before committing

This makes LLM-driven code modifications **trustworthy**.
