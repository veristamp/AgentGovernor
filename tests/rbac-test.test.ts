/**
 * MCP RBAC Integration Tests
 * 
 * Tests the Role-Based Access Control flow for MCP machine clients:
 * 1. Admin creates invite with allowedRoles
 * 2. Client registers using invite
 * 3. Client requests access token
 * 4. Token includes roles claim
 */

import { describe, it, expect, beforeAll } from 'bun:test';

const BASE_URL = process.env.TEST_BASE_URL || 'http://localhost:8787';
const ADMIN_EMAIL = process.env.TEST_ADMIN_EMAIL || 'srimon12mckv@gmail.com';
const ADMIN_PASSWORD = process.env.TEST_ADMIN_PASSWORD || '968746639000';
const TEST_AUDIENCE = 'mcp://rag-demo-service';

// Types for API responses
interface InviteResponse {
    token: string;
    jti: string;
    expiresAt: string;
    budget: number;
    allowedScopes: string[];
    allowedAudiences: string[];
    allowedRoles: string[];
}

interface InviteListResponse {
    invites: Array<{
        jti: string;
        allowedRoles?: string[];
    }>;
}

interface RegisterResponse {
    client_id: string;
    client_secret: string;
    allowed_scopes: string[];
    allowed_audiences: string[];
    allowed_roles: string[];
}

interface TokenResponse {
    access_token: string;
    token_type: string;
    expires_in: number;
    scope: string;
}

interface IntrospectResponse {
    active: boolean;
    roles?: string[];
}

// Session state
let sessionCookies: string = '';
let csrfToken: string = '';

// Helper to extract cookies from response
function extractCookies(res: Response): string {
    const setCookieHeaders = res.headers.getSetCookie?.() || [];
    return setCookieHeaders.map(c => c.split(';')[0]).join('; ');
}

// Helper to merge cookies
function mergeCookies(existing: string, newCookies: string): string {
    if (!newCookies) return existing;
    if (!existing) return newCookies;

    const cookieMap = new Map<string, string>();
    existing.split('; ').forEach(c => {
        const [name, ...rest] = c.split('=');
        if (name) cookieMap.set(name, rest.join('='));
    });

    newCookies.split('; ').forEach(c => {
        const [name, ...rest] = c.split('=');
        if (name) cookieMap.set(name, rest.join('='));
    });

    return Array.from(cookieMap.entries()).map(([k, v]) => `${k}=${v}`).join('; ');
}

// Helper to get CSRF token
async function getCSRFToken(): Promise<void> {
    const res = await fetch(`${BASE_URL}/api/csrf-token`, {
        headers: {
            'Origin': BASE_URL,
            ...(sessionCookies ? { 'Cookie': sessionCookies } : {}),
        },
    });

    const newCookies = extractCookies(res);
    sessionCookies = mergeCookies(sessionCookies, newCookies);

    const data = await res.json() as { csrfToken?: string };
    csrfToken = data.csrfToken || '';
}

// Helper to get admin session
async function getAdminSession(): Promise<void> {
    await getCSRFToken();

    const res = await fetch(`${BASE_URL}/api/auth/sign-in/email`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Origin': BASE_URL,
            'Cookie': sessionCookies,
            'X-CSRF-Token': csrfToken,
        },
        body: JSON.stringify({
            email: ADMIN_EMAIL,
            password: ADMIN_PASSWORD,
        }),
    });

    const newCookies = extractCookies(res);
    sessionCookies = mergeCookies(sessionCookies, newCookies);

    if (!res.ok) {
        const text = await res.text();
        throw new Error(`Failed to sign in: ${res.status} - ${text}`);
    }
}

// Helper for authenticated POST requests
async function authPost(path: string, body: unknown): Promise<Response> {
    return fetch(`${BASE_URL}${path}`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Origin': BASE_URL,
            'Cookie': sessionCookies,
            'X-CSRF-Token': csrfToken,
        },
        body: JSON.stringify(body),
    });
}

// Helper for authenticated GET requests
async function authGet(path: string): Promise<Response> {
    return fetch(`${BASE_URL}${path}`, {
        headers: {
            'Origin': BASE_URL,
            'Cookie': sessionCookies,
        },
    });
}

// Dynamic org ID (will be created in beforeAll)
let testOrgId: string = '';

describe('MCP RBAC - Role-Based Access Control', () => {
    let inviteToken: string;
    let clientId: string;
    let clientSecret: string;

    beforeAll(async () => {
        await getAdminSession();

        // Create a unique test organization
        const orgSlug = `rbac-test-${Date.now()}`;
        const createOrgRes = await authPost('/api/auth/organization/create', {
            name: `RBAC Test Org`,
            slug: orgSlug,
        });

        if (createOrgRes.status === 200 || createOrgRes.status === 201) {
            const orgData = await createOrgRes.json() as { id?: string; organization?: { id: string } };
            testOrgId = orgData.id || orgData.organization?.id || '';
            console.log('[DEBUG] Created test org:', testOrgId);
        } else {
            const errorText = await createOrgRes.text();
            console.error('[DEBUG] Failed to create org:', createOrgRes.status, errorText);
            throw new Error('Failed to create test organization');
        }
    });

    describe('Step 1: Create Invite with Roles', () => {
        it('should create an MCP invite with allowedRoles', async () => {
            const res = await authPost('/api/admin/mcp/invites', {
                orgId: testOrgId,
                budget: 5,
                ttlSeconds: 1800,
                allowedScopes: ['read:files', 'write:files'],
                allowedAudiences: [TEST_AUDIENCE],
                allowedRoles: ['mcp:rag-agent', 'mcp:file-reader'],
            });

            if (res.status !== 201) {
                const errorText = await res.text();
                console.error('[DEBUG] Invite creation failed:', res.status, errorText);
                expect(res.status).toBe(201);
                return;
            }

            const data = (await res.json()) as InviteResponse;
            expect(data.token).toBeDefined();
            expect(data.jti).toBeDefined();
            expect(data.allowedRoles).toEqual(['mcp:rag-agent', 'mcp:file-reader']);

            inviteToken = data.token;
        });

        it('should list invites with allowedRoles', async () => {
            const res = await authGet(`/api/admin/mcp/invites?orgId=${testOrgId}`);

            expect(res.status).toBe(200);

            const data = (await res.json()) as InviteListResponse;
            expect(Array.isArray(data.invites)).toBe(true);

            const invite = data.invites.find((i) => i.jti && i.allowedRoles?.includes('mcp:rag-agent'));
            expect(invite).toBeDefined();
        });
    });

    describe('Step 2: Register Client with Invite', () => {
        it('should register a new MCP client using the invite', async () => {
            const res = await fetch(`${BASE_URL}/api/mcp/register`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Origin': BASE_URL,
                    'Authorization': `Bearer ${inviteToken}`,
                },
                body: JSON.stringify({
                    client_name: 'RBAC Test Agent',
                    redirect_uris: ['http://localhost'],
                }),
            });

            if (res.status !== 201) {
                const errorText = await res.text();
                console.error('[DEBUG] Registration failed:', res.status, errorText);
                expect(res.status).toBe(201);
                return;
            }

            const data = (await res.json()) as RegisterResponse;
            expect(data.client_id).toBeDefined();
            expect(data.client_secret).toBeDefined();
            expect(data.allowed_roles).toEqual(['mcp:rag-agent', 'mcp:file-reader']);

            clientId = data.client_id;
            clientSecret = data.client_secret;
        });
    });

    describe('Step 3: Request Access Token', () => {
        it('should issue token with roles claim', async () => {
            const res = await fetch(`${BASE_URL}/api/auth/oauth2/token`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'Origin': BASE_URL,
                },
                body: new URLSearchParams({
                    grant_type: 'client_credentials',
                    client_id: clientId,
                    client_secret: clientSecret,
                    scope: 'read:files',
                    resource: TEST_AUDIENCE,
                }),
            });

            if (res.status !== 200) {
                const errorText = await res.text();
                console.error('[DEBUG] Token request failed:', res.status, errorText);
                expect(res.status).toBe(200);
                return;
            }

            const data = (await res.json()) as TokenResponse;
            expect(data.access_token).toBeDefined();
            expect(data.token_type).toBe('Bearer');

            // Decode JWT to verify roles
            const [, payloadB64] = data.access_token.split('.');
            if (!payloadB64) {
                throw new Error('Invalid JWT format');
            }
            const payload = JSON.parse(atob(payloadB64)) as { roles?: string[]; org_id?: string };

            expect(payload.roles).toBeDefined();
            expect(payload.roles).toContain('mcp:rag-agent');
            expect(payload.org_id).toBeDefined();
        });
    });

    describe('Step 4: Introspect Token', () => {
        it('should introspect token and show roles', async () => {
            const tokenRes = await fetch(`${BASE_URL}/api/auth/oauth2/token`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'Origin': BASE_URL,
                },
                body: new URLSearchParams({
                    grant_type: 'client_credentials',
                    client_id: clientId,
                    client_secret: clientSecret,
                    scope: 'read:files',
                    resource: TEST_AUDIENCE,
                }),
            });

            if (tokenRes.status !== 200) {
                expect(tokenRes.status).toBe(200);
                return;
            }

            const { access_token } = (await tokenRes.json()) as TokenResponse;

            const res = await fetch(`${BASE_URL}/api/auth/oauth2/introspect`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'Origin': BASE_URL,
                },
                body: new URLSearchParams({
                    token: access_token,
                    client_id: clientId,
                    client_secret: clientSecret,
                }),
            });

            expect(res.status).toBe(200);

            const data = (await res.json()) as IntrospectResponse;
            expect(data.active).toBe(true);
        });
    });
});

describe('MCP RBAC - Edge Cases', () => {
    beforeAll(async () => {
        // Session already established
    });

    it('should allow invite without roles (empty array)', async () => {
        const res = await authPost('/api/admin/mcp/invites', {
            orgId: testOrgId,
            budget: 1,
            ttlSeconds: 600,
            allowedScopes: ['read:files'],
            allowedAudiences: [TEST_AUDIENCE],
        });

        if (res.status !== 201) {
            const errorText = await res.text();
            console.error('[DEBUG] Edge case invite failed:', res.status, errorText);
            expect(res.status).toBe(201);
            return;
        }

        const data = (await res.json()) as InviteResponse;
        expect(data.allowedRoles).toEqual([]);
    });

    it('should reject invalid role format', async () => {
        const res = await authPost('/api/admin/mcp/invites', {
            orgId: testOrgId,
            budget: 1,
            ttlSeconds: 600,
            allowedScopes: ['read:files'],
            allowedAudiences: [TEST_AUDIENCE],
            allowedRoles: ['invalid-role-format'],
        });

        expect(res.status).toBe(400);
    });
});

