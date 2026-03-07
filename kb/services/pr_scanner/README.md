# PR Scanner - Automated Pull Request Review 🔍

**"Senior Engineer in a Bot"** - Automated PR review using the Judgment pipeline.

## Quick Start

### Scan a Local Diff

```python
from services.pr_scanner import create_pr_scanner

scanner = create_pr_scanner(project_root="f:/kb")

# Get diff from git
diff_text = subprocess.check_output(["git", "diff", "main...feature"]).decode()

# Scan
report = await scanner.scan_diff(
    diff_text=diff_text,
    pr_number=123,
    repo="veristamp/mykbos"
)

print(report.summary)
# ✅ APPROVE: 5/5 files passed (low risk)
```

### Scan a GitHub PR

```python
from services.pr_scanner import create_pr_service

service = create_pr_service(
    github_token="ghp_...",  # Or set GITHUB_TOKEN env var
    project_root="f:/kb"
)

# Scan and post comment
report = await service.scan_and_comment("veristamp/mykbos", 123)

# Or just scan without posting
report = await service.scan_pr("veristamp/mykbos", 123)
```

---

## Architecture

```
┌────────────────────────────────────────────────────────────────┐
│  PRService                   (High Level - Full Integration)   │
│  - Fetch PR from GitHub/GitLab                                 │
│  - Scan with PRScanner                                         │
│  - Post formatted comment                                      │
├────────────────────────────────────────────────────────────────┤
│  PRScanner                   (Mid Level - Core Logic)          │
│  - Parse diff into FileChanges                                 │
│  - Run JudgmentManager on each file                            │
│  - Aggregate into PRVerdictReport                              │
├────────────────────────────────────────────────────────────────┤
│  Components                  (Low Level - Utilities)           │
│  - DiffParser: Unified diff → FileChange                       │
│  - PRCommentFormatter: Report → Markdown                       │
│  - GitHubProvider: GitHub API calls                            │
├────────────────────────────────────────────────────────────────┤
│  Core                        (Data Structures)                 │
│  - PRVerdict, PRRiskLevel, FileChange                          │
│  - FileReviewResult, PRVerdictReport                           │
│  - PRScannerConfig                                             │
└────────────────────────────────────────────────────────────────┘
```

---

## Components

### PRService (High-Level)

End-to-end integration that:
1. Fetches PR from GitHub
2. Scans with PRScanner
3. Formats as Markdown
4. Posts comment back
5. Adds labels

```python
from services.pr_scanner import create_pr_service

service = create_pr_service(github_token="ghp_...")

# Full workflow
report = await service.scan_and_comment("owner/repo", 123)
```

### PRScanner (Core Logic)

Orchestrates the Judgment pipeline for each file:

```python
from services.pr_scanner import create_pr_scanner

scanner = create_pr_scanner(
    project_root="f:/kb",
    validate_syntax=True,
    check_duplicates=True,
    run_critic=True,
    run_impact=True,
    run_tests=False,  # Expensive
)

report = await scanner.scan_diff(diff_text, pr_number=123)
```

### DiffParser

Converts unified diff to structured data:

```python
from services.pr_scanner import parse_diff

changes = parse_diff(diff_text)
for change in changes:
    print(f"{change.path}: +{change.lines_added}/-{change.lines_removed}")
```

### PRCommentFormatter

Generates beautiful Markdown comments:

```python
from services.pr_scanner import format_pr_comment

markdown = format_pr_comment(report)
print(markdown)
```

---

## Verdict Mapping

The scanner maps Judgment gates to PR review feedback:

| Gate | PR Feedback |
|------|-------------|
| **Validator** | "Syntax error at line 42" |
| **Linter** | "Similar code exists in `utils.py:123`" |
| **Critic** | "PR too large - consider splitting" |
| **Oracle** | "⚠️ HIGH RISK: 15 callers affected" |
| **Immune** | "❌ Tests failed: `test_payments.py`" |

### Verdicts

| Verdict | Meaning |
|---------|---------|
| `APPROVE` | All checks passed |
| `REQUEST_CHANGES` | Critical issues found |
| `COMMENT` | Observations only |

### Risk Levels

| Level | Meaning |
|-------|---------|
| 🟢 LOW | Internal changes, few callers |
| 🟡 MEDIUM | Some callers, tests exist |
| 🟠 HIGH | Many callers, public API |
| 🔴 CRITICAL | Core infrastructure, no tests |

---

## Configuration

```python
from services.pr_scanner import PRScannerConfig

config = PRScannerConfig(
    # Gates
    validate_syntax=True,
    check_duplicates=True,
    run_critic=True,
    run_impact=True,
    run_tests=False,
    
    # Limits
    max_files_per_pr=100,
    max_lines_per_file=5000,
    
    # Skip patterns
    skip_patterns=[
        "*.lock",
        "*.min.js",
        "package-lock.json",
    ],
    
    # Auto-labeling
    auto_label=True,
    label_mapping={
        "critical": "⚠️ critical-risk",
        "high": "🟠 high-risk",
        "needs_tests": "🧪 needs-tests",
        "large_pr": "📦 large-pr",
    },
    
    # Thresholds
    large_pr_threshold=500,
)
```

---

## File Structure

```
services/pr_scanner/
├── __init__.py        # Clean exports
├── core.py            # Data structures
├── diff_parser.py     # Git diff parsing
├── scanner.py         # Main orchestrator
├── formatter.py       # Markdown formatting
├── service.py         # High-level integration
│
└── providers/         # Git hosting integrations
    ├── __init__.py
    ├── base.py        # Abstract provider
    └── github.py      # GitHub API
```

---

## Example Output

The formatter generates comments like:

```markdown
## ✅ PR Review: **APPROVE**

| Metric | Value |
|--------|-------|
| Risk Level | 🟢 LOW |
| Files Reviewed | 5 |
| Files Passed | 5/5 |
| Lines Changed | +42 / -15 |
| Scan Duration | 234ms |

### ✨ Summary

All automated checks passed. This PR is ready for human review.

### 📁 File Review

<details>
<summary>✅ Passed Files</summary>

#### ✅ `src/utils.py`

- 🔍 Syntax: ✓ Valid
- 📏 Critic: ✓ Score 95/100
- 🔮 Impact: low (2 callers)

</details>

---
*🤖 Automated review by **Veristamp PR Scanner** | 2024-12-28 12:30 UTC*
```

---

## GitHub Actions Integration

```yaml
name: PR Review
on:
  pull_request:
    types: [opened, synchronize]

jobs:
  review:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Run PR Scanner
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          python -c "
          import asyncio
          from services.pr_scanner import create_pr_service
          
          async def main():
              service = create_pr_service()
              await service.scan_and_comment(
                  '${{ github.repository }}',
                  ${{ github.event.pull_request.number }}
              )
          
          asyncio.run(main())
          "
```

---

## Future Extensions

- **GitLab MR Support**: Add `providers/gitlab.py`
- **Bitbucket PR Support**: Add `providers/bitbucket.py`
- **Webhook Server**: FastAPI endpoint for GitHub webhooks
- **Inline Comments**: Post comments on specific lines
- **Review Threads**: Create threaded discussions
