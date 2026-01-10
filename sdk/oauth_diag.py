#!/usr/bin/env python3
"""
OAuth Client Diagnostic Script

This script checks if an OAuth client exists and is properly configured.
"""

import asyncio
import httpx
import os
import sys

AUTH_SERVER = os.getenv("OAUTH_AUTH_SERVER", "http://localhost:8787")
CLIENT_ID = os.getenv("OAUTH_CLIENT_ID", "mEpsAJelUrwXdgicGRpUDOLiOHNgswLg")

async def main():
    print("=" * 60)
    print("  OAuth Client Diagnostic")
    print("=" * 60)
    print(f"\nAuth Server: {AUTH_SERVER}")
    print(f"Client ID:   {CLIENT_ID}")
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        # 1. Check OIDC discovery
        print("\n--- 1. OIDC Discovery ---")
        try:
            r = await client.get(f"{AUTH_SERVER}/.well-known/openid-configuration")
            if r.status_code == 200:
                discovery = r.json()
                print(f"✅ Discovery OK")
                print(f"   Issuer: {discovery.get('issuer')}")
                print(f"   Auth endpoint: {discovery.get('authorization_endpoint')}")
            else:
                print(f"❌ Discovery failed: {r.status_code}")
        except Exception as e:
            print(f"❌ Discovery error: {e}")
        
        # 2. Check public client info
        print("\n--- 2. Public Client Info ---")
        try:
            r = await client.get(
                f"{AUTH_SERVER}/api/auth/oauth2/public-client",
                params={"client_id": CLIENT_ID}
            )
            print(f"   Status: {r.status_code}")
            if r.status_code == 200:
                info = r.json()
                print(f"✅ Client found!")
                print(f"   Name: {info.get('name')}")
                print(f"   Icon: {info.get('icon')}")
                print(f"   URI: {info.get('uri')}")
            else:
                print(f"❌ Client not found or error")
                print(f"   Response: {r.text[:200]}")
        except Exception as e:
            print(f"❌ Client info error: {e}")
        
        # 3. Try authorize endpoint (follow redirects manually)
        print("\n--- 3. Authorize Endpoint Test ---")
        test_redirect_uri = "http://localhost:9000/callback"
        try:
            r = await client.get(
                f"{AUTH_SERVER}/api/auth/oauth2/authorize",
                params={
                    "client_id": CLIENT_ID,
                    "redirect_uri": test_redirect_uri,
                    "response_type": "code",
                    "scope": "openid",
                    "state": "test",
                    "code_challenge": "E9Mqx1i8lgMBKb0s1-7aI6A2BhNEz0vRphSiIpcB-Vs",
                    "code_challenge_method": "S256",
                },
                follow_redirects=False  # Don't follow redirects
            )
            print(f"   Status: {r.status_code}")
            location = r.headers.get("location", "")
            print(f"   Location: {location[:100]}...")
            
            if "/error" in location.lower():
                print(f"\n❌ OAuth Error detected!")
                # Check if error is in location
                from urllib.parse import parse_qs, urlparse
                if "?" in location:
                    parsed = urlparse(location)
                    qs = parse_qs(parsed.query)
                    if "error" in qs:
                        print(f"   Error: {qs.get('error')}")
                        print(f"   Description: {qs.get('error_description')}")
            elif "/signin" in location.lower() or "/login" in location.lower():
                print(f"\n⚠️ Redirecting to login (expected if no session)")
            elif "/consent" in location.lower():
                print(f"\n✅ Redirecting to consent (OAuth flow working!)")
            else:
                print(f"\n❓ Unexpected redirect")
                
        except Exception as e:
            print(f"❌ Authorize test error: {e}")
        
        print("\n" + "=" * 60)
        print("  Possible Issues:")
        print("=" * 60)
        print("""
1. CLIENT NOT FOUND
   - Client ID might be incorrect
   - Go to Console → OAuth Apps → check the client_id
   
2. REDIRECT_URI MISMATCH  
   - The registered redirect_uri must EXACTLY match
   - Go to Console → OAuth Apps → check Redirect URI
   - Should be: http://localhost:9000/callback
   
3. SCOPES NOT ALLOWED
   - Client might not have openid/profile/email enabled
   - Go to Console → OAuth Apps → check allowed scopes
""")

if __name__ == "__main__":
    asyncio.run(main())
