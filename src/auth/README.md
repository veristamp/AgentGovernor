# MCP Identity SDK - TypeScript

TypeScript SDK for MCP agents and resource servers to interact with the Mono Authz identity fabric.

## Features

| SDK | Use Case | Grant Type |
|-----|----------|------------|
| **MCPAgentClient** | AI agents, backend services | `client_credentials` |
| **MCPResourceServer** | Token validation | JWT or introspection |
| **MCPAdminClient** | Admin operations | Session-based |

## Quick Start

### Agent: Registration & Token Acquisition

```typescript
import { MCPAgentClient } from './src/auth';

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

// Fast path: JWT validation (stateless, ~0.1ms)
const result = await server.validateToken(token, {
  requiredScopes: ['read:data'],
  useJwt: true, // Default
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
| `useJwt: true` | Normal requests | ~0.1ms, stateless |
| `useJwt: false` | Opaque tokens | ~35ms, calls auth server |
| `requireActiveCheck: true` | Kill switch enforcement | Adds client status check |

## API Reference

### MCPAgentClient

| Method | Description |
|--------|-------------|
| `register(clientName, metadata?)` | Register a new machine client |
| `getToken(scopes?, audience?, forceRefresh?)` | Get access token (JWT if audience specified) |

### MCPResourceServer

| Method | Description |
|--------|-------------|
| `validateToken(token, options?)` | Validate token |
| `clearCache()` | Clear client status cache |

### MCPAdminClient

| Method | Description |
|--------|-------------|
| `login(email, password)` | Authenticate as admin |
| `createInvite(params)` | Create registration invite |
| `getClient(clientId)` | Get client details |
| `disableClient(clientId)` | Temporarily suspend client |
| `enableClient(clientId)` | Re-enable client |
| `revokeClient(clientId)` | Permanently revoke client |

### ValidationResult

| Field | Type | Description |
|-------|------|-------------|
| `valid` | `boolean` | Whether token is valid |
| `clientId` | `string` | Client identifier (from `azp` claim) |
| `orgId` | `string` | Organization ID |
| `scopes` | `string[]` | Granted scopes |
| `error` | `string` | Error message (if invalid) |
| `errorCode` | `string` | Error code (if invalid) |

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
```

## Files

```
src/auth/
├── index.ts           # Barrel export
├── types.ts           # Type definitions
├── errors.ts          # Error classes
├── jwt.ts             # JWT utilities
├── agent-client.ts    # MCPAgentClient
├── resource-server.ts # MCPResourceServer
├── admin-client.ts    # MCPAdminClient
├── helpers.ts         # Convenience functions
└── demo.ts            # Demo script
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
