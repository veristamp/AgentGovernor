# MCP Identity SDK - TypeScript

TypeScript SDK for MCP agents and resource servers to interact with the Mono Authz identity fabric.

> **Note**: This is a TypeScript port of the Python SDK (`sdk/mcp_identity.py`). We created this for native integration with the TypeScript MCPClientManager in Governed Code Mode.

## Why TypeScript SDK?

| Aspect | Python SDK | TypeScript SDK |
|--------|-----------|----------------|
| **MCPClientManager** | Requires bridge/spawn | ✅ Native integration |
| **Ed25519 Verification** | Not implemented | ✅ Web Crypto API |
| **Type Safety** | Type hints | ✅ Full static typing |
| **Runtime** | httpx async | Bun native fetch |

## Features

| SDK | Use Case | Grant Type |
|-----|----------|------------|
| **MCPAgentClient** | AI agents, backend services | `client_credentials` |
| **MCPResourceServer** | Token validation | JWT or introspection |
| **MCPAdminClient** | Admin operations | Session-based |

### RBAC Roles Support

Roles can be assigned to agents during invite creation and are embedded in access tokens:

```typescript
const invite = await admin.createInvite({
  orgId: 'org_123',
  budget: 5,
  allowedScopes: ['read:data', 'write:data'],
  allowedRoles: ['mcp:rag-agent', 'mcp:executor'],  // RBAC roles
});
```

## Quick Start

### Agent: Registration & Token Acquisition

```typescript
import { MCPAgentClient } from './src/core/auth';

const agent = new MCPAgentClient({
  authServer: 'https://auth.example.com',
  regJwt: 'eyJ...', // Registration invite from admin
});

// Register once (save credentials!)
const creds = await agent.register('my-rag-agent');
console.log(creds.clientId, creds.clientSecret);

// Get opaque token (no audience)
const token = await agent.getToken(['read:data']);

// Get JWT token with audience (RFC 8707)
const jwtToken = await agent.getToken(
  ['read:data'],
  'mcp://rag-service' // Triggers JWT issuance
);
```

### Resource Server: Token Validation

```typescript
import { MCPResourceServer } from './src/auth';

const server = new MCPResourceServer({
  authServer: 'https://auth.example.com',
  myAudience: 'mcp://rag-service',
});

// Fast path: JWT validation with signature verification (default)
const result = await server.validateToken(token, {
  requiredScopes: ['read:data'],
  useJwt: true,
  // verifySignature defaults to true
});

// With kill switch check (adds ~35ms for active check)
const resultWithCheck = await server.validateToken(token, {
  requiredScopes: ['admin:delete'],
  requireActiveCheck: true,
});

if (result.valid) {
  console.log(`Client: ${result.clientId}, Scopes: ${result.scopes}`);
} else {
  console.log(`Error: ${result.error} (${result.errorCode})`);
}
```

## Token Types

| Type | When Issued | Validation | Latency |
|------|-------------|------------|---------|
| **Opaque** | No `audience` parameter | Introspection (auth server call) | ~35ms |
| **JWT** | With `audience` parameter | Local JWKS verification | **~0.1ms** |

## Validation Modes

| Mode | Use Case | Performance |
|------|----------|-------------|
| `useJwt: true` | Normal requests (default verify) | ~1ms first, ~0.1ms cached |
| `useJwt: true, verifySignature: false` | Trusted internal/testing | ~0.1ms, stateless |
| `useJwt: false` | Opaque tokens | ~35ms, calls auth server |
| `requireActiveCheck: true` | Kill switch enforcement | Adds client status check |

## Ed25519 Signature Verification

The SDK uses Web Crypto API for Ed25519 JWT signature verification:

```typescript
// Production: verify signatures (default)
const result = await server.validateToken(token, {
  // verifySignature defaults to true (fetches JWKS, verifies Ed25519)
});

// If signature invalid:
if (result.errorCode === 'invalid_signature') {
  console.log('Token was tampered with!');
}
```

**How it works:**
1. Fetch `/.well-known/jwks.json` from auth server
2. Find key by `kid` from JWT header
3. Import Ed25519 public key via `crypto.subtle.importKey()`
4. Verify signature via `crypto.subtle.verify()`
5. Cache JWKS for 1 hour

## API Reference

### MCPAgentClient

| Method | Description |
|--------|-------------|
| `register(clientName, metadata?)` | Register a new machine client |
| `getToken(scopes?, audience?, forceRefresh?)` | Get access token (JWT if audience specified) |
| `getCredentials()` | Get saved credentials |

### MCPResourceServer

| Method | Description |
|--------|-------------|
| `validateToken(token, options?)` | Validate token |
| `clearCache()` | Clear client status and JWKS cache |

**ValidateTokenOptions:**
| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `requiredScopes` | `string[]` | `[]` | Scopes that must be present |
| `useJwt` | `boolean` | `true` | Use JWT validation (vs introspection) |
| `verifySignature` | `boolean` | `true` | Verify Ed25519 signature via JWKS |
| `requireActiveCheck` | `boolean` | `false` | Check kill switch status |

### MCPAdminClient

| Method | Description |
|--------|-------------|
| `login(email, password)` | Authenticate as admin |
| `createInvite(params)` | Create registration invite (with roles) |
| `getClient(clientId)` | Get client details |
| `disableClient(clientId)` | Temporarily suspend client |
| `enableClient(clientId)` | Re-enable client |
| `revokeClient(clientId)` | Permanently revoke client |

**CreateInviteParams:**
| Option | Type | Description |
|--------|------|-------------|
| `orgId` | `string` | Organization ID |
| `budget` | `number` | Max registrations allowed |
| `ttlMinutes` | `number` | Time to live in minutes |
| `allowedScopes` | `string[]` | Scopes agents can request |
| `allowedAudiences` | `string[]` | Valid audience values |
| `allowedRoles` | `string[]` | RBAC roles to assign |

### ValidationResult

| Field | Type | Description |
|-------|------|-------------|
| `valid` | `boolean` | Whether token is valid |
| `clientId` | `string` | Client identifier (from `azp` claim) |
| `orgId` | `string` | Organization ID |
| `scopes` | `string[]` | Granted scopes |
| `roles` | `string[]` | RBAC roles (from `roles` claim) |
| `error` | `string` | Error message (if invalid) |
| `errorCode` | `string` | Error code (if invalid) |

### Error Codes

| Code | Description |
|------|-------------|
| `missing_token` | No token provided |
| `invalid_token` | Token is malformed or unreadable |
| `invalid_signature` | Ed25519 signature verification failed |
| `token_expired` | JWT has expired |
| `audience_mismatch` | Token's `aud` doesn't match `my_audience` |
| `insufficient_scope` | Missing required scopes |
| `client_revoked` | Client has been permanently revoked |
| `client_disabled` | Client is temporarily disabled |
| `token_inactive` | Opaque token is inactive |
| `client_not_found` | Client lookup failed during introspection |
| `no_client_id` | Token missing `client_id` or `azp` |
| `jwt_validation_error` | JWT parsing/validation failed |
| `validation_error` | Generic validation error |
| `rate_limit_exceeded` | Rate limit exceeded |

## Integration with MCPClientManager

The TypeScript SDK is used natively by MCPClientManager:

```typescript
const manager = new MCPClientManager({
  enableAuth: true,
  authServer: 'https://auth.example.com',
  myAudience: 'mcp://gcm',
});

// Validates JWT at GATE 2 before executing any tool
await manager.executeAction(
  { actionType: 'tool', actionName: 'filesystem.read_file', arguments: { path: '.' } },
  { jwt: 'eyJ...' }  // Token validated here
);
```

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
```

## SDK Versioning

The SDK exposes version metadata and automatically sends it with outbound requests:

```typescript
import { SDK_VERSION, SDK_VERSION_HEADER, SDK_LANGUAGE_HEADER } from './src/auth';

console.log(SDK_VERSION);
// Requests include headers like:
// x-mcp-sdk-version: <SDK_VERSION>
// x-mcp-sdk-language: typescript
```

Update `SDK_VERSION` as part of your release process to keep telemetry and support alignment intact.

## Files

```
src/auth/
├── index.ts           # Barrel export
├── types.ts           # Type definitions
├── errors.ts          # Error classes
├── jwt.ts             # JWT decode utilities
├── jwks.ts            # JWKS fetching and Ed25519 verification
├── agent-client.ts    # MCPAgentClient
├── resource-server.ts # MCPResourceServer
├── admin-client.ts    # MCPAdminClient
├── helpers.ts         # Convenience functions
├── demo.ts            # Full demo script
└── README.md          # This file
```

## Run Demo

```bash
# Set environment variables
export SUPER_ADMIN_EMAIL=admin@example.com
export SUPER_ADMIN_PASSWORD=password
export MCP_AUTH_SERVER=http://localhost:8787

# Run demo
bun run src/auth/demo.ts
```

## Comparison with Python SDK

Both SDKs have feature parity:

| Feature | Python (`sdk/mcp_identity.py`) | TypeScript (`src/auth/`) |
|---------|-------------------------------|--------------------------|
| Agent Registration | ✅ | ✅ |
| Token Acquisition | ✅ Opaque + JWT | ✅ Opaque + JWT |
| JWT Validation | ✅ Decode only | ✅ Decode + Ed25519 verify |
| Introspection | ✅ | ✅ |
| Kill Switch | ✅ | ✅ |
| RBAC Roles | ✅ | ✅ |
| Admin Client | ✅ | ✅ |
| FastAPI Integration | ✅ `create_mcp_dependency()` | N/A |
| MCPClientManager | Requires bridge | ✅ Native |

**Use Python SDK** for:
- FastAPI backends
- Python MCP servers
- Data pipelines

**Use TypeScript SDK** for:
- Governed Code Mode executor
- Bun/Node.js services
- Native MCPClientManager integration
