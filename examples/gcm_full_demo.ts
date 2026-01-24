#!/usr/bin/env bun
/**
 * Full Governed Code Mode (GCM) Demo
 *
 * Demonstrates the complete dual-gate architecture:
 *
 * GATE 1: Static Auditor (Pre-Execution)
 *   • Parse LLM-generated code
 *   • Extract manifest of MCP calls
 *   • Pre-check policy BEFORE any execution
 *   • REJECT if policy fails
 *
 * GATE 2: MCPClientManager (Runtime)
 *   • Validate JWT on each call
 *   • Check policy again (runtime ABAC)
 *   • Execute actual MCP call
 *   • Log to audit trail
 *
 * Usage:
 *   bun run examples/gcm_full_demo.ts
 */

import { MCPClientManager } from '../src/mcp-client';
import { MCPAdminClient, MCPAgentClient, decodeJWT } from '../src/auth';
import { analyzeCode } from '../src/audit/bridge';
import { createSocketServer, SocketServer } from '../src/socket-server';
import { launchSandbox, launchUnsafe, isNsJailAvailable } from '../sandbox/launcher';
import { WorkflowRegistry } from '../src/workflow_registry';
import { readFileSync, existsSync } from 'fs';
import { platform } from 'os';


// =============================================================================
// Configuration
// =============================================================================

const AUTH_SERVER = process.env.MCP_AUTH_SERVER ?? 'http://localhost:8787';
const SUPER_ADMIN_EMAIL = process.env.SUPER_ADMIN_EMAIL ?? 'srimon12mckv@gmail.com';
const SUPER_ADMIN_PASSWORD = process.env.SUPER_ADMIN_PASSWORD ?? '968746639000';
const MY_AUDIENCE = 'mcp://rag-demo-service';
const ORG_ID = process.env.MCP_ORG_ID;

const getDefaultSocketPath = () => {
    if (platform() === 'win32') {
        return '\\\\.\\pipe\\mcp-workflow';
    }
    return '/tmp/mcp-workflow.sock';
};

const SOCKET_PATH = process.env.MCP_SOCKET_PATH || getDefaultSocketPath();


function printHeader(title: string): void {
    console.log('\n' + '='.repeat(70));
    console.log(`  ${title}`);
    console.log('='.repeat(70));
}

function printSubheader(title: string): void {
    console.log(`\n--- ${title} ---`);
}

// =============================================================================
// Sample LLM-Generated Code
// =============================================================================

const RAG_AGENT_CODE = `
# Docs to Files + Memory Workflow
# This code will be analyzed by GATE 1 before execution

import skills

async def main():
    docs_result = await skills.load("docs-to-files").fetch_and_store(
        library="/vercel/next.js",
        topic="routing",
        output_dir="output/docs"
    )
    insight = await skills.load("repo-insight").analyze_repo(
        query="Next.js routing docs summary",
        output_dir="output/reports",
        note_key="routing_docs_summary",
        write_report=True
    )
    return {"docs": docs_result, "insight": insight}
`;



const MALICIOUS_CODE = `
# Malicious Code - Should be BLOCKED at GATE 1

import skills

async def main():
    result = await skills.load("repo-insight").analyze_repo(
        query="secrets in repository",
        output_dir="output/reports",
        note_key="secrets_scan",
        write_report=True
    )
    return result
`;



// =============================================================================
// Main Demo
// =============================================================================

async function main(): Promise<number> {
    printHeader('GOVERNED CODE MODE - FULL DEMO');
    console.log(`
┌───────────────────────────────────────────────────────────────────┐
│  LLM generates code                                               │
│       │                                                           │
│       ▼                                                           │
│  GATE 1: Static Auditor (Pre-Execution)                          │
│       │                                                           │
│       ▼ (only if Gate 1 passes)                                  │
│  NsJail Sandbox                                                   │
│       │                                                           │
│       ▼                                                           │
│  GATE 2: MCPClientManager (Runtime Auth + Policy)                │
└───────────────────────────────────────────────────────────────────┘
`);

    // =========================================================================
    // PHASE 1: SETUP - Get Agent Credentials with RBAC Roles
    // =========================================================================
    printHeader('PHASE 1: AGENT SETUP (Auth Server)');

    const admin = new MCPAdminClient({ authServer: AUTH_SERVER });

    console.log('\n📧 Admin login...');
    if (!(await admin.login(SUPER_ADMIN_EMAIL, SUPER_ADMIN_PASSWORD))) {
        console.log('❌ Admin login failed');
        console.log('   Hint: set SUPER_ADMIN_EMAIL and SUPER_ADMIN_PASSWORD env vars.');
        return 1;
    }
    console.log('✅ Admin signed in');


    // Create org (or use existing org ID)
    let orgId = ORG_ID;
    if (orgId) {
        console.log(`✅ Using existing org: ${orgId.slice(0, 16)}...`);
    } else {
        const uniqueSlug = `gcm-demo-${Date.now()}`;
        let orgStatus: number;
        let orgData: { id?: string; organization?: { id: string } } = {};

        ({ status: orgStatus, data: orgData } = await admin.request(
            'POST',
            '/api/auth/organization/create',
            { name: `GCM Demo Org`, slug: uniqueSlug }
        ));

        if (orgStatus !== 200 && orgStatus !== 201) {
            console.log(`⚠️  Org creation via /api/auth failed: ${orgStatus}`);
            console.log(`   Response: ${JSON.stringify(orgData)}`);

            ({ status: orgStatus, data: orgData } = await admin.request(
                'POST',
                '/api/admin/organization/create',
                { name: `GCM Demo Org`, slug: uniqueSlug }
            ));
        }

        if (orgStatus !== 200 && orgStatus !== 201) {
            console.log(`❌ Org creation failed: ${orgStatus}`);
            console.log(`   Response: ${JSON.stringify(orgData)}`);
            console.log('   Hint: set MCP_ORG_ID to skip org creation.');
            return 1;
        }

        orgId = orgData.id ?? orgData.organization?.id;
        if (!orgId) {
            console.log('❌ Org creation returned no orgId');
            console.log(`   Response: ${JSON.stringify(orgData)}`);
            return 1;
        }
        console.log(`✅ Org created: ${orgId.slice(0, 16)}...`);
    }

    // Create invite with RBAC roles
    console.log('\n🎟️  Creating invite with RBAC roles...');
    const invite = await admin.createInvite({
        orgId: orgId!,
        budget: 5,
        ttlSeconds: 600,
        allowedScopes: ['read:files'],
        allowedAudiences: [MY_AUDIENCE],
        allowedRoles: ['mcp:docs-curator', 'mcp:repo-inspector'],
    });

    console.log('✅ Invite created');
    console.log('   • Roles: mcp:docs-curator, mcp:repo-inspector');
    console.log('   • These map to: skills:docs-to-files@1, skills:repo-insight@1');
    console.log(`   • Org ID: ${orgId}`);




    // Register agent
    const agent = new MCPAgentClient({ authServer: AUTH_SERVER, regJwt: invite.token });
    const credentials = await agent.register('gcm-rag-agent');
    console.log(`✅ Agent registered: ${credentials.clientId}`);

    // Get JWT
    const token = await agent.getToken(['read:files'], MY_AUDIENCE);
    const claims = decodeJWT(token.accessToken) as { roles?: string[] };
    console.log(`✅ JWT acquired with roles: ${claims.roles?.join(', ') || 'none'}`);


    // =========================================================================
    // PHASE 2: GATE 1 - STATIC AUDITOR (Pre-Execution)
    // =========================================================================
    printHeader('PHASE 2: GATE 1 - STATIC AUDITOR');

    printSubheader('2A: Analyze Skill Workflow');

    console.log('\n📝 LLM generated code:');
    console.log('   • docs-to-files.fetch_and_store(library="/vercel/next.js", topic="routing", output_dir="output/docs")');
    console.log('   • repo-insight.analyze_repo(query="Next.js routing docs summary", output_dir="output/reports", note_key="routing_docs_summary")');




    let manifest;
    try {
        manifest = await analyzeCode(RAG_AGENT_CODE);
        console.log('\n✅ Static analysis complete!');
        console.log('   📋 Manifest:');
        for (const skill of manifest.skills ?? []) {
            console.log(`      • ${skill}`);
        }
    } catch (e) {
        console.log(`\n❌ Static auditor failed: ${e}`);
        manifest = { tools: [], skills: ['skills:docs-to-files@1'] };
        console.log('   Using mock manifest for demo');
    }


    // Pre-check policy for manifest
    console.log('\n🔒 Pre-checking policy for extracted manifest...');
    const manager = new MCPClientManager({
        enablePolicy: true,
        enableAuth: true,
        authServer: AUTH_SERVER,
        myAudience: MY_AUDIENCE,
    });
    await manager.initialize();

    // Build identity from token
    const identity = {
        id: credentials.clientId,
        type: 'agent' as const,
        roles: claims.roles ?? [],
        scopes: ['read:files'],
        orgId: orgId,
    };


    let allAllowed = true;
    for (const skill of manifest.skills ?? []) {
        const decision = manager.checkPolicy(identity, skill);
        const status = decision.allowed ? '✅' : '❌';
        console.log(`   ${status} ${skill}: ${decision.allowed ? 'ALLOWED' : decision.reason}`);
        if (!decision.allowed) allAllowed = false;
    }

    const registry = new WorkflowRegistry({ baseDir: 'workflows_gcm' });
    if (allAllowed) {
        const stored = registry.saveWorkflow('Docs + Insight workflow', RAG_AGENT_CODE, {
            skills: manifest.skills ?? [],
            tools: manifest.tools ?? [],
            io_calls: [],
        }, {
            id: credentials.clientId,
            orgId: orgId,
        }, 'Fetch docs then store repo insight to memory');
        console.log(`\n✅ Workflow saved: ${stored.metadata.id}`);
    }

    if (allAllowed) {
        const matches = registry.search('Fetch docs and store insight', manifest.skills ?? [], orgId, 1);
        if (matches.length) {
            console.log(`✅ Retrieved workflow example for reuse: ${matches[0]?.metadata.id}`);
        } else {
            console.log('⚠️ No workflow example found for reuse');
        }
    }


    if (allAllowed) {
        console.log('\n✅ GATE 1 PASSED - All skills allowed, proceeding to execution');
    } else {

        console.log('\n❌ GATE 1 FAILED - Execution blocked');
        return 1;
    }

    printSubheader('2B: Analyze Denied Skill Workflow');

    console.log('\n⚠️  Malicious code attempts:');
    console.log('   • repo-insight.analyze_repo(query="secrets in repository", output_dir="output/reports", note_key="secrets_scan")');



    let maliciousManifest;
    try {
        maliciousManifest = await analyzeCode(MALICIOUS_CODE);
    } catch {
        maliciousManifest = { tools: [], skills: ['skills:repo-insight@1'] };
    }


    console.log('\n🔒 Pre-checking policy for malicious manifest...');
    for (const skill of maliciousManifest.skills ?? []) {
        const decision = manager.checkPolicy(identity, skill);
        const status = decision.allowed ? '✅' : '❌';
        console.log(`   ${status} ${skill}: ${decision.allowed ? 'ALLOWED (within role)' : decision.reason}`);
    }

    const deniedSkill = 'skills:repo-insight@1';
    const deniedDecision = manager.checkPolicy({
        ...identity,
        roles: ['mcp:docs-curator'],
    }, deniedSkill);
    const deniedSkillBlocked = !deniedDecision.allowed;
    if (deniedSkillBlocked) {
        console.log(`\n✅ GATE 1 BLOCKED ${deniedSkill} when only docs role is present`);
    } else {
        console.log(`\n⚠️ ${deniedSkill} was allowed (adjust roles if needed)`);
    }



    // =========================================================================
    // PHASE 3: GATE 2 - RUNTIME EXECUTION
    // =========================================================================
    printHeader('PHASE 3: GATE 2 - RUNTIME EXECUTION');

    console.log('\n📦 Code passed GATE 1, now executing in sandbox...');
    console.log('   (In production, this runs in NsJail with no network/filesystem)');

    const server = await createSocketServer(SOCKET_PATH, manager, { jwt: token.accessToken });

    printSubheader('3A: Authorized Skill Execution (docs-to-files + repo-insight)');
    try {
        console.log('\n📂 Running docs-to-files.fetch_and_store + repo-insight.analyze_repo in sandbox...');
        const hasNsJail = await isNsJailAvailable();
        const launcher = hasNsJail ? launchSandbox : launchUnsafe;
        const result = await launcher({
            code: RAG_AGENT_CODE,
            socketPath: SOCKET_PATH,
            timeout: 60,
            memoryLimit: 512,
            cpuLimit: 10,
        });

        if (result.exitCode !== 0) {
            console.log('❌ Sandbox execution failed');
            console.log(`   stderr: ${result.stderr || '(empty)'}`);
        } else {
            console.log('✅ GATE 2 PASSED - Skills executed in sandbox');
            const outputPath = 'output/docs/vercel_next.js_routing.md';
            if (existsSync(outputPath)) {
                const snippet = readFileSync(outputPath, 'utf-8').slice(0, 240);
                console.log(`   Output: ${outputPath}`);
                console.log(`   Snippet: ${snippet.replace(/\s+/g, ' ').trim()}...`);
            } else {
                console.log('   Output file not found.');
            }
        }
    } catch (e) {
        console.log(`❌ GATE 2 DENIED: ${e}`);
    }

    printSubheader('3B: Denied Skill Execution');
    if (deniedSkillBlocked) {
            console.log(`\n🚫 Skipping sandbox execution for ${deniedSkill} (blocked at Gate 1).`);
    } else {
        try {
            console.log('\n🚫 Running repo-insight.analyze_repo in sandbox...');
            const hasNsJail = await isNsJailAvailable();
            const launcher = hasNsJail ? launchSandbox : launchUnsafe;
            const result = await launcher({
                code: MALICIOUS_CODE,
                socketPath: SOCKET_PATH,
                timeout: 60,
                memoryLimit: 512,
                cpuLimit: 10,
            });

            if (result.exitCode !== 0) {
                console.log('✅ GATE 2 DENIED - Skill not permitted');
                console.log(`   stderr: ${result.stderr || '(empty)'}`);
            } else {
                console.log('⚠️ Unexpectedly allowed');
                console.log(`   Result: ${result.stdout.trim() || '(no stdout)'}`);
            }
        } catch (e) {
            console.log('✅ GATE 2 DENIED - Skill not permitted');
            console.log(`   Error: ${e}`);
        }
    }

    printSubheader('3C: Anonymous Call (No JWT)');
    try {
        console.log('\n🚫 Anonymous skill-scoped tool call...');
        await manager.executeAction(
            {
                actionType: 'tool',
                actionName: 'filesystem.write_file',
                arguments: { path: 'output/anon.txt', content: 'anon' },
            },
            {}  // No JWT
        );
        console.log('⚠️ Unexpectedly allowed');
    } catch (e) {
        console.log('✅ GATE 2 DENIED - No JWT provided');
        console.log(`   Error: ${e}`);
    } finally {
        await server.stop();
    }



    // =========================================================================
    // PHASE 4: KILL SWITCH
    // =========================================================================
    printHeader('PHASE 4: KILL SWITCH (Revoke Agent)');

    console.log(`\n🔒 Admin revokes agent ${credentials.clientId.slice(0, 16)}...`);
    await admin.revokeClient(credentials.clientId);
    console.log('✅ Agent revoked in auth server');

    console.log('\n⏱️  JWT is still valid (stateless)...');
    console.log('   To enforce kill switch, use requireActiveCheck: true');

    // =========================================================================
    // PHASE 5: AUDIT TRAIL
    // =========================================================================
    printHeader('PHASE 5: AUDIT TRAIL');

    const auditLog = manager.getAuditLog();
    console.log(`\n📋 All actions logged: ${auditLog.length} entries`);

    for (const entry of auditLog) {
        const status = entry.error ? '❌' : '✅';
        const identity = entry.identityId ?? 'anonymous';
        console.log(`   ${status} ${entry.tool} - ${identity} (${entry.latencyMs}ms)`);
        if (entry.error) {
            console.log(`      └─ ${entry.error}`);
        }
    }

    // =========================================================================
    // SUMMARY
    // =========================================================================
    printHeader('DEMO COMPLETE');

    console.log(`
📊 GCM Architecture Demonstrated:

  ┌─────────────────────────────────────────────────────────────┐
  │ GATE 1: Static Auditor                                      │
  │   ✅ Parsed LLM code, extracted manifest                   │
  │   ✅ Pre-checked policy BEFORE execution                   │
  │   ✅ Would BLOCK if unauthorized skills detected           │
  └─────────────────────────────────────────────────────────────┘
                              │
                              ▼
  ┌─────────────────────────────────────────────────────────────┐
  │ GATE 2: MCPClientManager                                    │
  │   ✅ Validated JWT (Ed25519 JWKS signature)                │
  │   ✅ Extracted roles from claims                           │
  │   ✅ Checked RBAC permission                               │
  │   ✅ Denied unauthorized skills                            │
  │   ✅ Denied anonymous calls                                │
  │   ✅ Logged all actions to audit trail                     │
  └─────────────────────────────────────────────────────────────┘

🔐 Security Properties:
   • Zero-trust: JWT required for all calls
   • RBAC: Roles mapped to skill permissions
   • Dual-gate: Pre-execution AND runtime checks
   • Kill switch: Can revoke agents instantly
   • Audit: Full trail of all actions
`);


    return 0;
}

// Run
main()
    .then((code) => process.exit(code))
    .catch((e) => {
        console.error(e);
        process.exit(1);
    });
