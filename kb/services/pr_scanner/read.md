✅ PR Scanner API Integration Complete
Created Files
API Models (
api/models/pr_scanner.py
) - 6.5 KB
python
# Request Models
- ScanDiffRequest      # Scan diff text directly
- ScanPRRequest        # Scan GitHub PR (with post_comment, add_labels options)
- ScanConfigRequest    # Override scanner settings
- WebhookPayload       # GitHub webhook payload
# Response Models  
- PRVerdictResponse    # Summary verdict
- PRVerdictDetailResponse  # Full verdict with per-file results
- FileReviewResultResponse # Single file result
- ScanStatusResponse   # Scanner health/config
- WebhookResponse      # Webhook processing status
# Enums
- PRVerdictEnum        # approve, request_changes, comment
- PRRiskLevelEnum      # low, medium, high, critical
API Routes (
api/routes/pr_scanner.py
) - 14.6 KB
📍 PR Scanner Endpoints:
GET    /v1/pr/status                              → Scanner status & config
POST   /v1/pr/scan/diff                           → Scan diff directly
POST   /v1/pr/scan/github                         → Scan GitHub PR
GET    /v1/pr/scan/github/{owner}/{repo}/{pr}     → Quick scan (GET)
POST   /v1/pr/webhook/github                      → GitHub webhook
POST   /v1/pr/format                              → Preview comment format
Dependencies (
api/deps.py
) - Updated
python
get_pr_scanner()   # Lazy-loaded scanner instance
get_pr_service()   # GitHub-enabled service (or None)
API Usage Examples
1. Check Status
bash
curl http://localhost:8000/v1/pr/status
json
{
  "available": true,
  "github_configured": true,
  "project_root": "f:/kb",
  "default_config": {
    "validate_syntax": true,
    "check_duplicates": true,
    "run_critic": true,
    "run_impact": true,
    "run_tests": false
  }
}
2. Scan a Diff Directly
bash
git diff main...feature | curl -X POST \
  -H "Content-Type: application/json" \
  -d '{"diff": "'"$(cat)"'", "pr_number": 123}' \
  http://localhost:8000/v1/pr/scan/diff
3. Scan a GitHub PR
bash
curl -X POST http://localhost:8000/v1/pr/scan/github \
  -H "Content-Type: application/json" \
  -d '{
    "repo": "veristamp/mykbos",
    "pr_number": 42,
    "post_comment": true,
    "add_labels": true
  }'
4. Quick Scan (GET)
bash
curl http://localhost:8000/v1/pr/scan/github/veristamp/mykbos/42
5. GitHub Webhook (CI/CD)
Configure in GitHub Settings → Webhooks:

Payload URL: https://your-domain/v1/pr/webhook/github
Content type: application/json
Events: Pull requests
Environment Variables
Variable	Description	Required
GITHUB_TOKEN	GitHub API token for PR access	For GitHub features
PROJECT_ROOT	Project root directory	Optional (defaults to cwd)
Architecture Summary
┌─────────────────────────────────────────────────────────────┐
│  API Layer (FastAPI)                                         │
│  └── routes/pr_scanner.py   →  /v1/pr/*                     │
│      └── models/pr_scanner.py (Pydantic)                    │
├─────────────────────────────────────────────────────────────┤
│  Service Layer                                               │
│  └── services/pr_scanner/                                   │
│      ├── PRService (High-Level)                             │
│      ├── PRScanner (Core Logic)                             │
│      ├── DiffParser, PRCommentFormatter                     │
│      └── providers/ (GitHubProvider)                        │
├─────────────────────────────────────────────────────────────┤
│  Judgment Layer (Reused)                                     │
│  └── judgment/                                               │
│      └── Validator, Linter, Critic, Oracle, Immune          │
└─────────────────────────────────────────────────────────────┘
The API is now industry-standard with proper Pydantic models, dependency injection, and webhook support for CI/CD integration! 🎉