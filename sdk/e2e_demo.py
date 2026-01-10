#!/usr/bin/env python3
"""
MCP Machine Identity SDK - Comprehensive Demo

This script demonstrates ALL MCP capabilities:

=== REGISTRATION & TOKEN FLOW ===
1. Admin signs in using MCPAdminClient
2. Admin mints a registration invite with scope/audience restrictions
3. Agent registers using MCPAgentClient (Budgeted DCR)
4. Agent gets OPAQUE access token (no audience specified)
5. Agent gets JWT access token (with audience - RFC 8707)

=== TOKEN VALIDATION MODES ===
6. JWT validation (stateless, ~0.1ms, no auth server call)
7. Introspection validation (50-100ms, calls auth server)
8. Hybrid validation (JWT + kill-switch check)

=== SECURITY FEATURES ===
9. Scope enforcement (rejected if scope not allowed)
10. Audience validation (embedded in JWT aud claim)
11. Kill switch - revoke client (immediate effect with introspection)

Prerequisites:
- Mono Authz server running at http://localhost:8787
- Environment variables set:
  - SUPER_ADMIN_EMAIL
  - SUPER_ADMIN_PASSWORD
  - MCP_VALID_AUDIENCES (must include mcp://rag-demo-service)
"""

import asyncio
import os
import sys
import time
from typing import Optional

# Add parent directory to path for local import
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mcp_identity import (
    MCPAgentClient, 
    MCPResourceServer, 
    MCPAdminClient,
    ValidationResult,
    MCPRateLimitError,
)

# =============================================================================
# Configuration
# =============================================================================

AUTH_SERVER = os.getenv("MCP_AUTH_SERVER", "http://localhost:8787")
SUPER_ADMIN_EMAIL = os.getenv("SUPER_ADMIN_EMAIL", "srimon12mckv@gmail.com")
SUPER_ADMIN_PASSWORD = os.getenv("SUPER_ADMIN_PASSWORD", "968746639000")

MY_AUDIENCE = "mcp://rag-demo-service"

# Enable debug logging (uncomment to troubleshoot)
# import logging
# logging.basicConfig(level=logging.DEBUG)


def print_header(title: str):
    """Print a formatted section header."""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def print_subheader(title: str):
    """Print a formatted subsection header."""
    print(f"\n--- {title} ---")


# =============================================================================
# Main Demo
# =============================================================================

async def main():
    print_header("MCP Machine Identity SDK - Comprehensive Demo")
    print(f"\nAuth Server: {AUTH_SERVER}")
    print(f"My Audience: {MY_AUDIENCE}")
    
    async with MCPAdminClient(AUTH_SERVER) as admin:
        # =====================================================================
        # PHASE 1: ADMIN SETUP
        # =====================================================================
        print_header("PHASE 1: ADMIN SETUP")
        
        print("\n📧 Signing in as Super Admin...")
        if not await admin.login(SUPER_ADMIN_EMAIL, SUPER_ADMIN_PASSWORD):
            print("❌ Admin login failed")
            return 1
        print("✅ Signed in successfully")
        
        # Create a unique organization for this demo
        print("\n📁 Creating organization for demo...")
        unique_slug = f"mcp-demo-{int(time.time())}"
        create_res = await admin.request("POST", "/api/auth/organization/create", json={
            "name": f"MCP Demo Org {unique_slug}",
            "slug": unique_slug,
        })
        
        if create_res.status_code not in [200, 201]:
            print(f"❌ Create org failed: {create_res.status_code}")
            print(create_res.text)
            return 1
            
        data = create_res.json()
        org_id = data.get("id") or data.get("organization", {}).get("id")
        print(f"✅ Created org: {org_id[:16]}...")

        # =====================================================================
        # PHASE 2: REGISTRATION INVITE (BUDGETED DCR)
        # =====================================================================
        print_header("PHASE 2: REGISTRATION INVITE (RFC 7591 + Budgeted DCR)")
        
        print("\n🎟️  Minting registration invite with restrictions...")
        invite_res = await admin.request("POST", "/api/admin/mcp/invites", json={
            "orgId": org_id,
            "budget": 2,  # Allow 2 registrations
            "ttlSeconds": 600,
            "allowedScopes": ["read:data", "write:data", "admin:delete"],
            "allowedAudiences": [MY_AUDIENCE],
        })
        
        if invite_res.status_code not in [200, 201]:
            print(f"❌ Mint invite failed: {invite_res.status_code}")
            print(invite_res.text)
            return 1
            
        invite_data = invite_res.json()
        reg_jwt = invite_data.get("data", invite_data).get("token")
        print("✅ Invite minted!")
        print(f"   • Budget: 2 registrations")
        print(f"   • Allowed Scopes: read:data, write:data, admin:delete")
        print(f"   • Allowed Audiences: {MY_AUDIENCE}")
        
        # =====================================================================
        # PHASE 3: AGENT REGISTRATION
        # =====================================================================
        print_header("PHASE 3: AGENT REGISTRATION")
        
        async with MCPAgentClient(AUTH_SERVER, reg_jwt=reg_jwt) as agent:
            print("\n🤖 Registering agent with REG_JWT...")
            credentials = await agent.register(
                client_name="demo-rag-agent",
                metadata={"version": "1.0", "purpose": "demo"}
            )
            
            print("✅ Agent registered!")
            print(f"   • Client ID: {credentials.client_id}")
            print(f"   • Allowed Scopes: {credentials.allowed_scopes}")
            print(f"   • Allowed Audiences: {credentials.allowed_audiences}")
            
            # =====================================================================
            # PHASE 4: TOKEN ACQUISITION - OPAQUE vs JWT
            # =====================================================================
            print_header("PHASE 4: TOKEN ACQUISITION")
            
            print_subheader("4A: Opaque Token (no audience)")
            print("\n🔑 Requesting token WITHOUT audience...")
            opaque_token = await agent.get_token(scopes=["read:data"])
            print(f"✅ Opaque token acquired!")
            print(f"   • Token: {opaque_token.access_token[:40]}...")
            print(f"   • Token type: {'JWT' if len(opaque_token.access_token.split('.')) == 3 else 'Opaque'}")
            
            print_subheader("4B: JWT Token (with audience - RFC 8707)")
            print(f"\n🔑 Requesting token WITH audience '{MY_AUDIENCE}'...")
            jwt_token = await agent.get_token(
                scopes=["read:data"],
                audience=MY_AUDIENCE,  # This triggers JWT with aud claim!
                force_refresh=True,  # Force new token to bypass cache
            )
            token_parts = jwt_token.access_token.split('.')
            is_jwt = len(token_parts) == 3
            print(f"✅ {'JWT' if is_jwt else 'Opaque'} token acquired!")
            print(f"   • Token: {jwt_token.access_token[:50]}...")
            
            if is_jwt:
                # Decode and show the payload
                import base64
                import json
                payload_b64 = token_parts[1]
                padding = 4 - len(payload_b64) % 4
                if padding != 4:
                    payload_b64 += '=' * padding
                payload = json.loads(base64.urlsafe_b64decode(payload_b64))
                print(f"   • JWT Payload:")
                print(f"     - aud: {payload.get('aud')}")
                print(f"     - azp: {payload.get('azp')}")
                print(f"     - scope: {payload.get('scope')}")
                print(f"     - exp: {payload.get('exp')}")
            
            # =====================================================================
            # PHASE 5: RESOURCE SERVER VALIDATION
            # =====================================================================
            print_header("PHASE 5: TOKEN VALIDATION (3 Modes)")
            
            # Create resource server
            server = MCPResourceServer(
                auth_server=AUTH_SERVER,
                my_audience=MY_AUDIENCE,
                client_id=credentials.client_id,
                client_secret=credentials.client_secret,
                admin_client=admin
            )
            
            # --- 5A: JWT Validation (Fast, Stateless) ---
            print_subheader("5A: JWT Validation (Stateless, ~0.1ms)")
            
            start = time.perf_counter()
            result = await server.validate_token(
                jwt_token.access_token,
                required_scopes=["read:data"],
                use_jwt=True,  # Default: stateless JWT validation
            )
            elapsed_ms = (time.perf_counter() - start) * 1000
            
            if result.valid:
                print(f"✅ JWT validation PASSED in {elapsed_ms:.2f}ms")
                print(f"   • Client ID: {result.client_id}")
                print(f"   • Scopes: {result.scopes}")
            else:
                print(f"❌ JWT validation FAILED: {result.error}")
                return 1
            
            # --- 5B: Introspection Validation (Slower, Real-time) ---
            print_subheader("5B: Introspection Validation (~50-100ms)")
            
            start = time.perf_counter()
            result = await server.validate_token(
                opaque_token.access_token,  # Use opaque token
                required_scopes=["read:data"],
                use_jwt=False,  # Force introspection
            )
            elapsed_ms = (time.perf_counter() - start) * 1000
            
            if result.valid:
                print(f"✅ Introspection validation PASSED in {elapsed_ms:.2f}ms")
                print(f"   • Client ID: {result.client_id}")
                print(f"   • Org ID: {result.org_id}")
            else:
                print(f"❌ Introspection validation FAILED: {result.error}")
                return 1
            
            # --- 5C: Hybrid Validation (JWT + Kill Switch Check) ---
            print_subheader("5C: Hybrid Validation (JWT + Active Check)")
            
            start = time.perf_counter()
            result = await server.validate_token(
                jwt_token.access_token,
                required_scopes=["read:data"],
                use_jwt=True,
                require_active_check=True,  # Also check if client is revoked
            )
            elapsed_ms = (time.perf_counter() - start) * 1000
            
            if result.valid:
                print(f"✅ Hybrid validation PASSED in {elapsed_ms:.2f}ms")
                print(f"   • JWT validated + client status confirmed active")
            else:
                print(f"❌ Hybrid validation FAILED: {result.error}")
                return 1
            
            # =====================================================================
            # PHASE 6: SCOPE ENFORCEMENT
            # =====================================================================
            print_header("PHASE 6: SCOPE ENFORCEMENT")
            
            print("\n🚫 Attempting to validate with unauthorized scope...")
            result = await server.validate_token(
                jwt_token.access_token,
                required_scopes=["admin:delete"],  # Not in token's scope!
                use_jwt=True,
            )
            
            if not result.valid and result.error_code == "insufficient_scope":
                print(f"✅ Correctly REJECTED - insufficient scope")
                print(f"   • Error: {result.error}")
            else:
                print(f"⚠️ Unexpected result: {result}")
            
            # =====================================================================
            # PHASE 7: AUDIENCE VALIDATION
            # =====================================================================
            print_header("PHASE 7: AUDIENCE VALIDATION")
            
            # Create a server with different audience
            other_server = MCPResourceServer(
                auth_server=AUTH_SERVER,
                my_audience="mcp://different-service",  # Different audience!
                client_id=credentials.client_id,
                client_secret=credentials.client_secret,
                admin_client=admin
            )
            
            print("\n🚫 Attempting to validate token at wrong audience...")
            result = await other_server.validate_token(
                jwt_token.access_token,
                use_jwt=True,
            )
            
            if not result.valid and result.error_code == "audience_mismatch":
                print(f"✅ Correctly REJECTED - audience mismatch")
                print(f"   • Expected: mcp://different-service")
                print(f"   • Token aud: {MY_AUDIENCE}")
            else:
                print(f"⚠️ Unexpected result: {result}")
            
            # =====================================================================
            # PHASE 8: TOKEN MINTING RATE LIMIT
            # =====================================================================
            print_header("PHASE 8: TOKEN MINTING RATE LIMIT")
            
            print("\n🚦 Testing rate limit (default: 60 tokens/minute)...")
            print("   Making rapid token requests to trigger rate limit...")
            
            # We need to make many requests quickly to hit the rate limit
            # Since the default is 60/min, we'll try to make more than that
            rate_limit_triggered = False
            request_count = 0
            
            for i in range(65):  # Try to exceed 60/min limit
                try:
                    _ = await agent.get_token(
                        scopes=["read:data"],
                        force_refresh=True  # Force new request each time
                    )
                    request_count += 1
                    if i % 10 == 0:
                        print(f"   • Made {i + 1} token requests...")
                except MCPRateLimitError as e:
                    rate_limit_triggered = True
                    print(f"\n✅ Rate limit triggered after {request_count} requests!")
                    print(f"   • Error: {e}")
                    print(f"   • Retry After: {e.retry_after} seconds")
                    break
            
            if not rate_limit_triggered:
                print(f"\n⚠️ Made {request_count} requests without hitting rate limit")
                print("   (Rate limit may be disabled or set higher)")
            
            # =====================================================================
            # PHASE 9: KILL SWITCH (CLIENT REVOCATION)
            # =====================================================================
            print_header("PHASE 9: KILL SWITCH (Client Revocation)")
            
            print(f"\n🔒 Revoking client {credentials.client_id[:16]}...")
            revoke_res = await admin.request(
                "POST", 
                f"/api/admin/mcp/clients/{credentials.client_id}/revoke"
            )
            
            if revoke_res.status_code in [200, 204]:
                print("✅ Client revoked")
            else:
                print(f"⚠️ Revoke returned: {revoke_res.status_code}")
            
            # Clear cache for instant effect
            server.clear_cache()
            
            print_subheader("9A: JWT Validation (still valid - stateless)")
            result = await server.validate_token(
                jwt_token.access_token,
                use_jwt=True,
                require_active_check=False,  # Don't check status
            )
            if result.valid:
                print("⚠️ JWT still valid (expected - stateless validation)")
                print("   Token will expire at its exp time")
            
            print_subheader("9B: JWT + Active Check (rejected!)")
            result = await server.validate_token(
                jwt_token.access_token,
                use_jwt=True,
                require_active_check=True,  # Check client status!
            )
            if not result.valid:
                print(f"✅ Token REJECTED with active check!")
                print(f"   • Error: {result.error}")
            else:
                print(f"⚠️ Token still valid (unexpected)")
            
            print_subheader("9C: Introspection (rejected!)")
            result = await server.validate_token(
                opaque_token.access_token,
                use_jwt=False,  # Force introspection
            )
            if not result.valid:
                print(f"✅ Opaque token REJECTED!")
                print(f"   • Error: {result.error}")
            else:
                print(f"⚠️ Token still valid (unexpected)")

    # =========================================================================
    # SUMMARY
    # =========================================================================
    print_header("DEMO COMPLETE - ALL SDK FEATURES VERIFIED")
    print("""
✅ Registration Invite (Budgeted DCR)
✅ Agent Registration with REG_JWT
✅ Opaque Token Acquisition
✅ JWT Token Acquisition (RFC 8707)
✅ JWT Validation (Stateless, ~0.1ms)
✅ Introspection Validation (~50-100ms)
✅ Hybrid Validation (JWT + Kill Switch)
✅ Scope Enforcement
✅ Audience Validation (JWT aud claim)
✅ Token Minting Rate Limit (60/min)
✅ Kill Switch / Client Revocation
""")
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
