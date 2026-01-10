# Mono Authz Python SDK

Two authentication SDKs in one package:

| SDK | Use Case | Grant Type |
|-----|----------|------------|
| **MCP Machine Identity** | AI agents, backend services | `client_credentials` |
| **OAuth User Auth** | User-facing apps, SSO | `authorization_code` + PKCE |

## Features

### MCP Machine Identity (M2M)
- **Agent Registration** — Register machine clients using budgeted invite tokens (REG_JWT)
- **Token Acquisition** — Get opaque or JWT access tokens with automatic caching
- **JWT Validation** — Stateless validation (~0.1ms) using Ed25519 signatures
- **Kill Switch** — Real-time client revocation with optional active checks
- **FastAPI Integration** — Ready-to-use dependency injection

### OAuth User Authentication
- **Authorization Code Flow** — Full OAuth 2.1 with PKCE
- **Token Management** — Refresh, introspect, and revoke tokens
- **User Info** — Fetch user profile from userinfo endpoint
- **FastAPI Demo** — Complete login flow example


## Installation

```bash
pip install mcp-identity

# With FastAPI integration
pip install mcp-identity[fastapi]
```

## Quick Start

### Agent: Registration & Token Acquisition

```python
from mcp_identity import MCPAgentClient

async with MCPAgentClient(
    auth_server="https://auth.example.com",
    reg_jwt="eyJ..."  # Registration invite from admin
) as agent:
    
    # Register once (save credentials!)
    creds = await agent.register("my-rag-agent")
    print(f"Client ID: {creds.client_id}")
    print(f"Secret: {creds.client_secret}")  # Store securely!
    
    # Get opaque token (no audience)
    token = await agent.get_token(scopes=["read:data"])
    
    # Get JWT token with audience (RFC 8707)
    jwt_token = await agent.get_token(
        scopes=["read:data"],
        audience="mcp://rag-service"  # Triggers JWT issuance
    )
```

### Resource Server: Token Validation

```python
from mcp_identity import MCPResourceServer

server = MCPResourceServer(
    auth_server="https://auth.example.com",
    my_audience="mcp://rag-service",
)

# Fast path: JWT validation (stateless, ~0.1ms)
result = await server.validate_token(
    token,
    required_scopes=["read:data"],
    use_jwt=True,  # Default: local signature verification
)

# With kill switch check (adds ~35ms for active check)
result = await server.validate_token(
    token,
    required_scopes=["admin:delete"],
    require_active_check=True,  # Check if client is revoked
)

if result.valid:
    print(f"✅ Client: {result.client_id}, Scopes: {result.scopes}")
else:
    print(f"❌ {result.error} ({result.error_code})")
```

### FastAPI Integration

```python
from fastapi import FastAPI, Depends
from mcp_identity import create_mcp_dependency, ValidationResult

app = FastAPI()

validate_mcp = create_mcp_dependency(
    auth_server="https://auth.example.com",
    my_audience="mcp://rag-service",
    required_scopes=["read:data"],
)

@app.get("/query")
async def query(client: ValidationResult = Depends(validate_mcp)):
    return {"client_id": client.client_id, "org_id": client.org_id}
```

## Token Types

| Type | When Issued | Validation | Latency |
|------|-------------|------------|---------|
| **Opaque** | No `audience` parameter | Introspection (auth server call) | ~35ms |
| **JWT** | With `audience` parameter | Local JWKS verification | **~0.1ms** |

### Request JWT Token (RFC 8707)

```python
# Pass 'audience' to get JWT with embedded aud claim
token = await agent.get_token(
    scopes=["read:data"],
    audience="mcp://rag-service"
)
# Result: eyJhbGciOiJFZERTQSIsImtpZCI6Ii...
```

## Validation Modes

| Mode | Use Case | Performance |
|------|----------|-------------|
| `use_jwt=True` | Normal requests | ~0.1ms, stateless |
| `use_jwt=False` | Opaque tokens | ~35ms, calls auth server |
| `require_active_check=True` | Kill switch enforcement | Adds client status check |

```python
# Standard validation (fast)
result = await server.validate_token(token, use_jwt=True)

# With kill switch (for high-risk operations)
result = await server.validate_token(
    token,
    required_scopes=["admin:delete"],
    require_active_check=True
)
```

## Security Model

### Agent Flow (Client Credentials)

```
1. Admin mints registration invite (REG_JWT)
2. Agent registers → receives client_id + client_secret
3. Agent requests tokens with scopes + optional audience
4. Access tokens are short-lived (5-10 minutes)
```

### Resource Server Flow

```
1. Extract Bearer token from request
2. If JWT: Verify Ed25519 signature locally (~0.1ms)
3. If opaque: Call introspection endpoint (~35ms)
4. Check audience (JWT aud claim vs my_audience)
5. Check required scopes
6. Optional: Check client is still active (kill switch)
```

### Kill Switch

| Action | Effect | Latency |
|--------|--------|---------|
| **Revoke** | Permanent termination | Instant with `require_active_check=True` |
| **Disable** | Temporary suspension | Instant with `require_active_check=True` |

For stateless JWT validation, revoked tokens remain valid until expiration.
Use `require_active_check=True` for immediate revocation enforcement.

## API Reference

### MCPAgentClient

| Method | Description |
|--------|-------------|
| `register(client_name, metadata)` | Register a new machine client |
| `get_token(scopes, audience, force_refresh)` | Get access token (JWT if audience specified) |
| `close()` | Close HTTP client |

### MCPResourceServer

| Method | Description |
|--------|-------------|
| `validate_token(token, required_scopes, use_jwt, require_active_check)` | Validate token |
| `clear_cache()` | Clear client status cache |
| `close()` | Close HTTP client |

### ValidationResult

| Field | Type | Description |
|-------|------|-------------|
| `valid` | `bool` | Whether token is valid |
| `client_id` | `str` | Client identifier (from `azp` claim) |
| `org_id` | `str` | Organization ID |
| `scopes` | `list[str]` | Granted scopes |
| `error` | `str` | Error message (if invalid) |
| `error_code` | `str` | Error code (if invalid) |

### Error Codes

| Code | Description |
|------|-------------|
| `token_expired` | JWT has expired |
| `audience_mismatch` | Token's `aud` doesn't match `my_audience` |
| `insufficient_scope` | Missing required scopes |
| `client_revoked` | Client has been permanently revoked |
| `client_disabled` | Client is temporarily disabled |
| `token_inactive` | Opaque token is inactive |

## Environment Variables

```bash
# Auth server
MCP_AUTH_SERVER=https://auth.example.com

# For agents
MCP_REG_JWT=eyJ...              # Registration invite
MCP_CLIENT_ID=mcp_xxx           # After registration
MCP_CLIENT_SECRET=secret        # After registration

# For resource servers
MCP_MY_AUDIENCE=mcp://my-service
MCP_ADMIN_API_KEY=pk_live_...   # For client status checks
```

## Performance

Tested on localhost with Ed25519 JWT validation:

| Operation | Latency |
|-----------|---------|
| JWT validation (stateless) | **0.07ms** |
| Introspection validation | 36ms |
| JWT + active check | 12ms |

**JWT validation is 500x faster than introspection.**

---

## OAuth User Authentication

For user-facing applications that need to authenticate users via OAuth 2.1.

### Quick Start

```python
from oauth_client import OAuthClient

oauth = OAuthClient(
    auth_server="https://auth.example.com",
    client_id="your-client-id",
    client_secret="your-client-secret",
    redirect_uri="http://localhost:9000/callback",
    scopes=["openid", "profile", "email"],
)

# 1. Generate authorization URL
auth_url, state, code_verifier = oauth.get_authorization_url()
# Redirect user to auth_url

# 2. Handle callback - exchange code for tokens
tokens = await oauth.exchange_code(code, state, code_verifier)

# 3. Get user info
user = await oauth.get_user_info(tokens.access_token)
print(f"Hello, {user.name}!")

# 4. Refresh token when expired
if tokens.is_expired:
    new_tokens = await oauth.refresh_tokens(tokens.refresh_token)
```

### Run the Demo App

1. **Create an OAuth app** in the console:
   - Go to Console → OAuth Apps → Create App
   - Set Redirect URI to `http://localhost:9000/callback`
   - Copy client_id and client_secret

2. **Set environment variables**:
   ```bash
   export OAUTH_CLIENT_ID="your-client-id"
   export OAUTH_CLIENT_SECRET="your-client-secret"
   export OAUTH_AUTH_SERVER="http://localhost:8787"
   ```

3. **Run the demo**:
   ```bash
   cd sdk/python
   uv run python oauth_demo.py
   ```

4. **Open browser**: http://localhost:9000

### The OAuth Flow

```
1. User visits /login → Redirects to auth server
2. User authenticates (email + password)
3. User selects organization (if org scopes requested + multiple orgs)
4. User consents to permissions
5. Auth server redirects back with authorization code
6. App exchanges code for tokens
7. App can now access user info and protected resources
```

### OAuthClient API

| Method | Description |
|--------|-------------|
| `get_authorization_url()` | Generate login URL with PKCE |
| `exchange_code(code, state)` | Exchange auth code for tokens |
| `get_user_info(access_token)` | Fetch user profile |
| `refresh_tokens(refresh_token)` | Refresh access token |
| `introspect_token(token)` | Check token validity |
| `revoke_token(token)` | Revoke a token |
| `get_logout_url()` | Get logout URL |

### OAuthTokens

| Field | Type | Description |
|-------|------|-------------|
| `access_token` | `str` | Bearer token for API calls |
| `refresh_token` | `str` | Token for refreshing access |
| `id_token` | `str` | JWT with user identity |
| `expires_in` | `int` | Seconds until expiration |
| `is_expired` | `bool` | Check if token expired |

### OAuthUser

| Field | Type | Description |
|-------|------|-------------|
| `sub` | `str` | User ID (subject) |
| `email` | `str` | User email |
| `name` | `str` | User display name |
| `picture` | `str` | Avatar URL |
| `org_id` | `str` | Organization ID (if org scope) |
| `org_role` | `str` | User's role in org |

## License

MIT

