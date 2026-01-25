#!/usr/bin/env python3
"""
OAuth 2.1 User Flow Demo - FastAPI Application

This demo application shows the complete user-facing OAuth 2.1 flow:

=== THE FLOW ===
1. User visits /login → Redirects to auth server
2. User authenticates (email + password)
3. User selects organization (if multiple orgs and org scopes requested)
4. User consents to permissions
5. Auth server redirects back to /callback with code
6. App exchanges code for tokens
7. App shows user info at /me

=== PREREQUISITES ===
1. Create an OAuth app in the console:
   - Go to Console → OAuth Apps → Create App
   - Name: "Demo App"
   - Type: Web Application
   - Redirect URI: http://localhost:9000/callback
   - Scopes: openid, profile, email
   - Save the client_id and client_secret

2. Set environment variables:
   export OAUTH_CLIENT_ID="your-client-id"
   export OAUTH_CLIENT_SECRET="your-client-secret"
   export OAUTH_AUTH_SERVER="http://localhost:8787"

3. Run the demo:
   cd sdk/python
   uv run python oauth_demo.py

4. Open http://localhost:9000 in your browser

=== ENDPOINTS ===
GET /            → Home page with login button
GET /login       → Initiates OAuth flow (redirects to auth server)
GET /callback    → Handles OAuth callback, exchanges code for tokens
GET /me          → Shows logged-in user info
GET /refresh     → Refreshes access token
GET /logout      → Logs out user
"""

import os
import sys
import json
import uvicorn
from contextlib import asynccontextmanager

# Add parent directory to path for local import
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from starlette.middleware.sessions import SessionMiddleware

from oauth_client import OAuthClient, OAuthTokens, OAuthUser, OAuthError

# =============================================================================
# Configuration
# =============================================================================

AUTH_SERVER = os.getenv("OAUTH_AUTH_SERVER", "http://localhost:8787")
CLIENT_ID = os.getenv("OAUTH_CLIENT_ID", "EKpHJwNFcACkbEhQiOxKOVUKJTGmYUOZ")
CLIENT_SECRET = os.getenv("OAUTH_CLIENT_SECRET", "IFYsYjBIvRddHQdORKOzcvSPlmKCnCHh")
REDIRECT_URI = os.getenv("OAUTH_REDIRECT_URI", "http://localhost:9000/callback")

# Scopes to request (add org scopes to trigger SelectOrgPage)
# SCOPES = ["openid", "profile", "email"]

# Add org scopes to demonstrate organization selection
# Add offline_access to get refresh tokens
SCOPES = ["openid", "profile", "email", "read:organization", "offline_access"]

# Session secret (generate a real one in production!)
SESSION_SECRET = os.getenv("SESSION_SECRET", "demo-secret-change-me-in-production")

# Global OAuth client
oauth_client: OAuthClient = None


# =============================================================================
# Application Setup
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize OAuth client on startup."""
    global oauth_client
    
    if not CLIENT_ID:
        print("\n" + "=" * 70)
        print("  ⚠️  CONFIGURATION REQUIRED")
        print("=" * 70)
        print("""
To run this demo, you need to:

1. Create an OAuth app in the console:
   - Go to http://localhost:8787/console
   - Navigate to OAuth Apps → Create App
   - Set Redirect URI to: http://localhost:9000/callback
   - Copy the client_id and client_secret

2. Set environment variables:
   export OAUTH_CLIENT_ID="your-client-id"
   export OAUTH_CLIENT_SECRET="your-client-secret"

3. Run again:
   uv run python oauth_demo.py
""")
        print("=" * 70 + "\n")
        sys.exit(1)
    
    oauth_client = OAuthClient(
        auth_server=AUTH_SERVER,
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        redirect_uri=REDIRECT_URI,
        scopes=SCOPES,
    )
    
    await oauth_client.__aenter__()
    
    print("\n" + "=" * 70)
    print("  🚀 OAuth Demo App Running")
    print("=" * 70)
    print(f"  Auth Server: {AUTH_SERVER}")
    print(f"  Client ID:   {CLIENT_ID}")
    print(f"  Redirect:    {REDIRECT_URI}")
    print(f"  Scopes:      {', '.join(SCOPES)}")
    print("=" * 70)
    print("\n  Open http://localhost:9000 in your browser\n")
    
    yield
    
    await oauth_client.__aexit__(None, None, None)


app = FastAPI(
    title="OAuth 2.1 Demo",
    description="Demonstrates user-facing OAuth 2.1 flow",
    lifespan=lifespan,
)

# Add session middleware for storing tokens
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    session_cookie="oauth_demo_session",
    max_age=3600,
)


# =============================================================================
# HTML Templates
# =============================================================================

def render_page(title: str, content: str, user: OAuthUser = None) -> HTMLResponse:
    """Render a simple HTML page."""
    nav = ""
    if user:
        nav = f"""
        <div style="display: flex; align-items: center; gap: 1rem;">
            <span>👤 {user.name or user.email}</span>
            <a href="/me" class="btn">My Profile</a>
            <a href="/refresh" class="btn btn-secondary">Refresh Token</a>
            <a href="/logout" class="btn btn-danger">Logout</a>
        </div>
        """
    else:
        nav = '<a href="/login" class="btn">Login with OAuth</a>'
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>{title} - OAuth Demo</title>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            * {{ box-sizing: border-box; }}
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                margin: 0;
                padding: 2rem;
            }}
            .container {{
                max-width: 800px;
                margin: 0 auto;
            }}
            .card {{
                background: white;
                border-radius: 16px;
                box-shadow: 0 20px 60px rgba(0,0,0,0.2);
                padding: 2rem;
                margin-bottom: 1rem;
            }}
            .header {{
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 2rem;
                padding-bottom: 1rem;
                border-bottom: 1px solid #eee;
            }}
            .logo {{
                font-size: 1.5rem;
                font-weight: bold;
                background: linear-gradient(135deg, #667eea, #764ba2);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
            }}
            h1 {{ color: #333; margin-top: 0; }}
            pre {{
                background: #f4f4f4;
                padding: 1rem;
                border-radius: 8px;
                overflow-x: auto;
                font-size: 0.85rem;
            }}
            .btn {{
                display: inline-block;
                padding: 0.75rem 1.5rem;
                background: linear-gradient(135deg, #667eea, #764ba2);
                color: white;
                text-decoration: none;
                border-radius: 8px;
                font-weight: 500;
                transition: transform 0.2s, box-shadow 0.2s;
            }}
            .btn:hover {{
                transform: translateY(-2px);
                box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
            }}
            .btn-secondary {{
                background: #f4f4f4;
                color: #333;
            }}
            .btn-danger {{
                background: #dc3545;
            }}
            .info-grid {{
                display: grid;
                grid-template-columns: 150px 1fr;
                gap: 0.5rem 1rem;
            }}
            .info-grid dt {{ font-weight: 600; color: #666; }}
            .info-grid dd {{ margin: 0; word-break: break-all; }}
            .badge {{
                display: inline-block;
                padding: 0.25rem 0.5rem;
                background: #e0e7ff;
                color: #3730a3;
                border-radius: 4px;
                font-size: 0.75rem;
                font-weight: 600;
            }}
            .success {{ color: #059669; }}
            .flow-diagram {{
                background: #f8fafc;
                border-radius: 8px;
                padding: 1.5rem;
                margin: 1rem 0;
            }}
            .flow-step {{
                display: flex;
                align-items: flex-start;
                gap: 1rem;
                margin-bottom: 1rem;
            }}
            .flow-number {{
                width: 28px;
                height: 28px;
                background: linear-gradient(135deg, #667eea, #764ba2);
                color: white;
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                font-weight: bold;
                font-size: 0.85rem;
                flex-shrink: 0;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="card">
                <div class="header">
                    <div class="logo">🔐 OAuth 2.1 Demo</div>
                    {nav}
                </div>
                <h1>{title}</h1>
                {content}
            </div>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(html)


# =============================================================================
# Routes
# =============================================================================

@app.get("/")
async def home(request: Request):
    """Home page showing the OAuth flow."""
    
    tokens = request.session.get("tokens")
    user = None
    
    if tokens:
        try:
            user = await oauth_client.get_user_info(tokens["access_token"])
        except:
            pass
    
    if user:
        content = f"""
        <p class="success">✅ You are logged in!</p>
        <div class="info-grid">
            <dt>Name</dt><dd>{user.name}</dd>
            <dt>Email</dt><dd>{user.email}</dd>
            <dt>User ID</dt><dd><code>{user.sub}</code></dd>
        </div>
        <p style="margin-top: 2rem;">
            <a href="/me" class="btn">View Full Profile</a>
        </p>
        """
    else:
        content = """
        <p>This demo shows the complete OAuth 2.1 Authorization Code flow with PKCE.</p>
        
        <div class="flow-diagram">
            <div class="flow-step">
                <div class="flow-number">1</div>
                <div>
                    <strong>Click "Login with OAuth"</strong><br>
                    <small>You'll be redirected to the authorization server</small>
                </div>
            </div>
            <div class="flow-step">
                <div class="flow-number">2</div>
                <div>
                    <strong>Authenticate</strong><br>
                    <small>Sign in with your email and password</small>
                </div>
            </div>
            <div class="flow-step">
                <div class="flow-number">3</div>
                <div>
                    <strong>Select Organization</strong> <span class="badge">If applicable</span><br>
                    <small>Choose which organization to authorize (if you have multiple)</small>
                </div>
            </div>
            <div class="flow-step">
                <div class="flow-number">4</div>
                <div>
                    <strong>Consent</strong><br>
                    <small>Review and approve the requested permissions</small>
                </div>
            </div>
            <div class="flow-step">
                <div class="flow-number">5</div>
                <div>
                    <strong>Callback</strong><br>
                    <small>You're redirected back here with tokens</small>
                </div>
            </div>
        </div>
        
        <p style="text-align: center; margin-top: 2rem;">
            <a href="/login" class="btn" style="font-size: 1.1rem; padding: 1rem 2rem;">
                🚀 Start OAuth Flow
            </a>
        </p>
        """
    
    return render_page("Welcome", content, user)


@app.get("/login")
async def login(request: Request):
    """Initiate OAuth flow - redirects to auth server."""
    
    # Generate authorization URL with PKCE
    auth_url, state, code_verifier = oauth_client.get_authorization_url()
    
    # Store code_verifier in session for callback
    request.session["oauth_state"] = state
    request.session["code_verifier"] = code_verifier
    
    print(f"\n📤 Redirecting to authorization endpoint...")
    print(f"   State: {state}")
    print(f"   URL: {auth_url[:100]}...")
    
    return RedirectResponse(auth_url)


@app.get("/callback")
async def callback(request: Request, code: str = None, state: str = None, error: str = None, error_description: str = None):
    """Handle OAuth callback - exchange code for tokens."""
    
    # Check for errors
    if error:
        content = f"""
        <p style="color: #dc3545;">❌ Authorization failed</p>
        <div class="info-grid">
            <dt>Error</dt><dd>{error}</dd>
            <dt>Description</dt><dd>{error_description or 'N/A'}</dd>
        </div>
        <p><a href="/" class="btn">Try Again</a></p>
        """
        return render_page("Authorization Error", content)
    
    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code")
    
    # Verify state
    stored_state = request.session.get("oauth_state")
    if state != stored_state:
        raise HTTPException(status_code=400, detail="Invalid state parameter")
    
    # Get stored code_verifier
    code_verifier = request.session.get("code_verifier")
    
    print(f"\n📥 Received callback!")
    print(f"   Code: {code[:20]}...")
    print(f"   State: {state}")
    
    try:
        # Exchange code for tokens
        tokens = await oauth_client.exchange_code(code, state, code_verifier)
        
        print(f"\n✅ Tokens received!")
        print(f"   Access Token: {tokens.access_token[:30]}...")
        print(f"   Refresh Token: {tokens.refresh_token[:30] if tokens.refresh_token else 'None'}...")
        print(f"   Expires In: {tokens.expires_in}s")
        
        # Store tokens in session
        request.session["tokens"] = {
            "access_token": tokens.access_token,
            "refresh_token": tokens.refresh_token,
            "id_token": tokens.id_token,
            "expires_at": tokens.expires_at,
        }
        
        # Clear OAuth state
        request.session.pop("oauth_state", None)
        request.session.pop("code_verifier", None)
        
        return RedirectResponse("/me")
        
    except OAuthError as e:
        content = f"""
        <p style="color: #dc3545;">❌ Token exchange failed</p>
        <div class="info-grid">
            <dt>Error</dt><dd>{e.code or 'unknown'}</dd>
            <dt>Message</dt><dd>{str(e)}</dd>
            <dt>Description</dt><dd>{e.description or 'N/A'}</dd>
        </div>
        <p><a href="/" class="btn">Try Again</a></p>
        """
        return render_page("Token Error", content)


@app.get("/me")
async def me(request: Request):
    """Show current user info."""
    
    tokens = request.session.get("tokens")
    
    if not tokens:
        return RedirectResponse("/login")
    
    try:
        user = await oauth_client.get_user_info(tokens["access_token"])
        
        content = f"""
        <div class="info-grid">
            <dt>User ID (sub)</dt><dd><code>{user.sub}</code></dd>
            <dt>Name</dt><dd>{user.name or 'N/A'}</dd>
            <dt>Email</dt><dd>{user.email or 'N/A'}</dd>
            <dt>Email Verified</dt><dd>{'✅ Yes' if user.email_verified else '❌ No'}</dd>
            <dt>Picture</dt><dd>{'<img src="' + user.picture + '" width="50" style="border-radius: 50%">' if user.picture else 'N/A'}</dd>
        </div>
        
        <h3 style="margin-top: 2rem;">🎫 Token Info</h3>
        <div class="info-grid">
            <dt>Access Token</dt><dd><code style="font-size: 0.7rem;">{tokens['access_token'][:50]}...</code></dd>
            <dt>Refresh Token</dt><dd><code style="font-size: 0.7rem;">{tokens.get('refresh_token', 'None')[:50] if tokens.get('refresh_token') else 'None'}...</code></dd>
            <dt>ID Token</dt><dd>{'Present ✅' if tokens.get('id_token') else 'None'}</dd>
        </div>
        
        <h3 style="margin-top: 2rem;">📦 Additional Claims</h3>
        <pre>{json.dumps(user.extra, indent=2) if user.extra else 'None'}</pre>
        """
        
        return render_page("My Profile", content, user)
        
    except OAuthError as e:
        # Token might be expired, try refresh
        if tokens.get("refresh_token"):
            return RedirectResponse("/refresh")
        
        request.session.clear()
        return RedirectResponse("/login")


@app.get("/refresh")
async def refresh(request: Request):
    """Refresh access token."""
    
    tokens = request.session.get("tokens")
    
    if not tokens or not tokens.get("refresh_token"):
        return RedirectResponse("/login")
    
    try:
        new_tokens = await oauth_client.refresh_tokens(tokens["refresh_token"])
        
        # Update session
        request.session["tokens"] = {
            "access_token": new_tokens.access_token,
            "refresh_token": new_tokens.refresh_token or tokens["refresh_token"],
            "id_token": new_tokens.id_token,
            "expires_at": new_tokens.expires_at,
        }
        
        content = """
        <p class="success">✅ Token refreshed successfully!</p>
        <p><a href="/me" class="btn">View Profile</a></p>
        """
        return render_page("Token Refreshed", content)
        
    except OAuthError as e:
        request.session.clear()
        content = f"""
        <p style="color: #dc3545;">❌ Token refresh failed: {e}</p>
        <p><a href="/login" class="btn">Login Again</a></p>
        """
        return render_page("Refresh Error", content)


@app.get("/logout")
async def logout(request: Request):
    """Log out user."""
    
    tokens = request.session.get("tokens")
    
    # Clear session first
    request.session.clear()
    
    # Optionally revoke refresh token
    if tokens and tokens.get("refresh_token"):
        try:
            await oauth_client.revoke_token(tokens["refresh_token"])
            print("✅ Refresh token revoked")
        except:
            pass
    
    # Get logout URL
    id_token = tokens.get("id_token") if tokens else None
    logout_url = oauth_client.get_logout_url(
        id_token=id_token,
        post_logout_redirect="http://localhost:9000",
    )
    
    content = """
    <p class="success">✅ You have been logged out.</p>
    <p><a href="/" class="btn">Return Home</a></p>
    """
    return render_page("Logged Out", content)


@app.get("/debug/tokens")
async def debug_tokens(request: Request):
    """Debug endpoint to view raw token data."""
    tokens = request.session.get("tokens", {})
    return JSONResponse({
        "tokens": {
            "access_token": tokens.get("access_token", "")[:50] + "..." if tokens.get("access_token") else None,
            "refresh_token": tokens.get("refresh_token", "")[:50] + "..." if tokens.get("refresh_token") else None,
            "id_token": "present" if tokens.get("id_token") else None,
            "expires_at": tokens.get("expires_at"),
        }
    })


# =============================================================================
# Main
# =============================================================================

if __name__ == "__main__":
    uvicorn.run(
        "oauth_demo:app",
        host="0.0.0.0",
        port=9000,
        reload=True,
    )
