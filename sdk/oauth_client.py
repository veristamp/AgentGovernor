"""
OAuth 2.1 User Authentication SDK - Python

A lightweight SDK for integrating user-facing OAuth 2.1 authentication
with the Mono Authz identity platform.

This SDK supports:
- Authorization Code Flow with PKCE (recommended for all apps)
- Token refresh
- Token introspection  
- User info retrieval
- Logout

Usage - FastAPI Integration:
    from oauth_client import OAuthClient, FastAPIIntegration
    from fastapi import FastAPI
    
    app = FastAPI()
    
    oauth = OAuthClient(
        auth_server="https://auth.example.com",
        client_id="your-client-id",
        client_secret="your-client-secret",
        redirect_uri="http://localhost:8000/callback",
        scopes=["openid", "profile", "email"],
    )
    
    # Add OAuth routes
    FastAPIIntegration(app, oauth)
    
    # Now you have:
    # GET /login -> Redirects to auth server
    # GET /callback -> Handles OAuth callback
    # GET /logout -> Logs out user
    # GET /me -> Returns current user info

Usage - Manual Integration:
    # Generate authorization URL
    auth_url, state, code_verifier = oauth.get_authorization_url()
    
    # Exchange code for tokens (after callback)
    tokens = await oauth.exchange_code(code, code_verifier)
    
    # Get user info
    user = await oauth.get_user_info(tokens.access_token)
    
    # Refresh token
    new_tokens = await oauth.refresh_token(tokens.refresh_token)
"""

import httpx
import hashlib
import base64
import secrets
import json
import time
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Callable
from urllib.parse import urlencode, parse_qs, urlparse
import logging

logger = logging.getLogger(__name__)


# =============================================================================
# Exceptions
# =============================================================================

class OAuthError(Exception):
    """Base exception for OAuth errors."""
    def __init__(self, message: str, code: Optional[str] = None, description: Optional[str] = None):
        super().__init__(message)
        self.code = code
        self.description = description


class OAuthAuthorizationError(OAuthError):
    """Error during authorization flow."""
    pass


class OAuthTokenError(OAuthError):
    """Error during token operations."""
    pass


class OAuthSessionError(OAuthError):
    """Error related to user session."""
    pass


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class OAuthTokens:
    """OAuth tokens returned from token endpoint."""
    access_token: str
    token_type: str = "Bearer"
    expires_in: int = 3600
    refresh_token: Optional[str] = None
    id_token: Optional[str] = None
    scope: Optional[str] = None
    
    # Computed fields
    expires_at: float = field(default=0.0)
    
    def __post_init__(self):
        if self.expires_at == 0.0:
            self.expires_at = time.time() + self.expires_in
    
    @property
    def is_expired(self) -> bool:
        """Check if access token is expired (with 30s buffer)."""
        return time.time() >= (self.expires_at - 30)


@dataclass 
class OAuthUser:
    """User info from userinfo endpoint or ID token."""
    sub: str  # Subject (user ID)
    email: Optional[str] = None
    email_verified: Optional[bool] = None
    name: Optional[str] = None
    picture: Optional[str] = None
    
    # Organization context (if requested)
    org_id: Optional[str] = None
    org_slug: Optional[str] = None
    org_role: Optional[str] = None
    
    # Additional claims
    extra: Dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OAuthUser":
        """Create OAuthUser from dictionary."""
        known_fields = {"sub", "email", "email_verified", "name", "picture", 
                       "org_id", "org_slug", "org_role"}
        extra = {k: v for k, v in data.items() if k not in known_fields}
        return cls(
            sub=data.get("sub", ""),
            email=data.get("email"),
            email_verified=data.get("email_verified"),
            name=data.get("name"),
            picture=data.get("picture"),
            org_id=data.get("org_id"),
            org_slug=data.get("org_slug"), 
            org_role=data.get("org_role"),
            extra=extra,
        )


@dataclass
class OAuthDiscovery:
    """OAuth 2.0 Authorization Server Metadata (RFC 8414)."""
    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    userinfo_endpoint: Optional[str] = None
    jwks_uri: Optional[str] = None
    registration_endpoint: Optional[str] = None
    introspection_endpoint: Optional[str] = None
    revocation_endpoint: Optional[str] = None
    end_session_endpoint: Optional[str] = None
    scopes_supported: List[str] = field(default_factory=list)
    response_types_supported: List[str] = field(default_factory=list)
    grant_types_supported: List[str] = field(default_factory=list)
    code_challenge_methods_supported: List[str] = field(default_factory=list)


# =============================================================================
# PKCE Helpers
# =============================================================================

def generate_pkce_pair() -> tuple[str, str]:
    """
    Generate PKCE code verifier and challenge.
    
    Returns:
        Tuple of (code_verifier, code_challenge)
    """
    # Generate random 43-128 character verifier
    code_verifier = secrets.token_urlsafe(32)
    
    # Create S256 challenge
    digest = hashlib.sha256(code_verifier.encode()).digest()
    code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    
    return code_verifier, code_challenge


def generate_state() -> str:
    """Generate random state parameter for CSRF protection."""
    return secrets.token_urlsafe(24)


# =============================================================================
# OAuth Client
# =============================================================================

class OAuthClient:
    """
    OAuth 2.1 Client for user authentication.
    
    Supports Authorization Code Flow with PKCE (RFC 7636).
    """
    
    def __init__(
        self,
        auth_server: str,
        client_id: str,
        client_secret: Optional[str] = None,  # Optional for public clients
        redirect_uri: str = "http://localhost:8000/callback",
        scopes: List[str] = None,
        auto_discover: bool = True,
    ):
        """
        Initialize OAuth client.
        
        Args:
            auth_server: Base URL of the authorization server
            client_id: OAuth client ID
            client_secret: OAuth client secret (None for public clients)
            redirect_uri: Callback URL for authorization
            scopes: Default scopes to request
            auto_discover: Whether to fetch discovery document on init
        """
        self.auth_server = auth_server.rstrip("/")
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.scopes = scopes or ["openid", "profile", "email"]
        self.is_public = client_secret is None
        
        # Discovery document (lazy loaded)
        self._discovery: Optional[OAuthDiscovery] = None
        self._http_client: Optional[httpx.AsyncClient] = None
        
        # Pending auth states
        self._pending_states: Dict[str, Dict[str, str]] = {}
    
    async def __aenter__(self):
        self._http_client = httpx.AsyncClient(timeout=30.0)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._http_client:
            await self._http_client.aclose()
    
    @property
    def http(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=30.0)
        return self._http_client
    
    async def discover(self) -> OAuthDiscovery:
        """
        Fetch OAuth discovery document.
        
        Returns:
            OAuthDiscovery with all endpoints
        """
        if self._discovery:
            return self._discovery
        
        # Try well-known endpoint
        url = f"{self.auth_server}/.well-known/openid-configuration"
        
        try:
            response = await self.http.get(url)
            response.raise_for_status()
            data = response.json()
            
            self._discovery = OAuthDiscovery(
                issuer=data.get("issuer", self.auth_server),
                authorization_endpoint=data.get("authorization_endpoint", f"{self.auth_server}/api/auth/authorize"),
                token_endpoint=data.get("token_endpoint", f"{self.auth_server}/api/auth/oauth2/token"),
                userinfo_endpoint=data.get("userinfo_endpoint", f"{self.auth_server}/api/auth/userinfo"),
                jwks_uri=data.get("jwks_uri"),
                introspection_endpoint=data.get("introspection_endpoint"),
                revocation_endpoint=data.get("revocation_endpoint"),
                end_session_endpoint=data.get("end_session_endpoint"),
                scopes_supported=data.get("scopes_supported", []),
                response_types_supported=data.get("response_types_supported", ["code"]),
                grant_types_supported=data.get("grant_types_supported", ["authorization_code"]),
                code_challenge_methods_supported=data.get("code_challenge_methods_supported", ["S256"]),
            )
        except Exception as e:
            logger.warning(f"Discovery failed, using defaults: {e}")
            self._discovery = OAuthDiscovery(
                issuer=self.auth_server,
                authorization_endpoint=f"{self.auth_server}/api/auth/authorize",
                token_endpoint=f"{self.auth_server}/api/auth/oauth2/token",
                userinfo_endpoint=f"{self.auth_server}/api/auth/userinfo",
            )
        
        return self._discovery
    
    def get_authorization_url(
        self,
        scopes: Optional[List[str]] = None,
        state: Optional[str] = None,
        extra_params: Optional[Dict[str, str]] = None,
    ) -> tuple[str, str, str]:
        """
        Generate authorization URL for user login.
        
        Args:
            scopes: Scopes to request (defaults to client scopes)
            state: Custom state parameter (auto-generated if not provided)
            extra_params: Additional query parameters
        
        Returns:
            Tuple of (authorization_url, state, code_verifier)
        """
        # Generate PKCE pair
        code_verifier, code_challenge = generate_pkce_pair()
        
        # Generate or use provided state
        state = state or generate_state()
        
        # Build authorization URL
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": " ".join(scopes or self.scopes),
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "prompt": "consent",  # Force consent screen even if previously approved
        }
        
        if extra_params:
            params.update(extra_params)
        
        # Store pending state for verification
        self._pending_states[state] = {
            "code_verifier": code_verifier,
            "created_at": str(time.time()),
        }
        
        # Use discovery endpoint or default
        auth_endpoint = f"{self.auth_server}/api/auth/oauth2/authorize"
        if self._discovery:
            auth_endpoint = self._discovery.authorization_endpoint
        
        auth_url = f"{auth_endpoint}?{urlencode(params)}"
        
        return auth_url, state, code_verifier
    
    async def exchange_code(
        self,
        code: str,
        state: Optional[str] = None,
        code_verifier: Optional[str] = None,
    ) -> OAuthTokens:
        """
        Exchange authorization code for tokens.
        
        Args:
            code: Authorization code from callback
            state: State parameter to verify (required if stored)
            code_verifier: PKCE code verifier (auto-retrieved from stored state)
        
        Returns:
            OAuthTokens with access_token, refresh_token, etc.
        """
        # Verify state and get code_verifier
        if state and state in self._pending_states:
            stored = self._pending_states.pop(state)
            code_verifier = code_verifier or stored.get("code_verifier")
        
        if not code_verifier:
            raise OAuthAuthorizationError(
                "Missing code_verifier for PKCE",
                code="pkce_error"
            )
        
        # Build token request
        discovery = await self.discover()
        
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.redirect_uri,
            "client_id": self.client_id,
            "code_verifier": code_verifier,
        }
        
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        
        # Add client authentication
        if self.client_secret:
            data["client_secret"] = self.client_secret
        
        try:
            response = await self.http.post(
                discovery.token_endpoint,
                data=data,
                headers=headers,
            )
            
            if not response.is_success:
                error_data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
                raise OAuthTokenError(
                    f"Token exchange failed: {response.status_code}",
                    code=error_data.get("error"),
                    description=error_data.get("error_description"),
                )
            
            token_data = response.json()
            return OAuthTokens(
                access_token=token_data["access_token"],
                token_type=token_data.get("token_type", "Bearer"),
                expires_in=token_data.get("expires_in", 3600),
                refresh_token=token_data.get("refresh_token"),
                id_token=token_data.get("id_token"),
                scope=token_data.get("scope"),
            )
            
        except httpx.HTTPError as e:
            raise OAuthTokenError(f"Token request failed: {e}")
    
    async def refresh_tokens(self, refresh_token: str) -> OAuthTokens:
        """
        Refresh access token using refresh token.
        
        Args:
            refresh_token: Valid refresh token
        
        Returns:
            New OAuthTokens
        """
        discovery = await self.discover()
        
        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": self.client_id,
        }
        
        if self.client_secret:
            data["client_secret"] = self.client_secret
        
        try:
            response = await self.http.post(
                discovery.token_endpoint,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            
            if not response.is_success:
                error_data = response.json() if "application/json" in response.headers.get("content-type", "") else {}
                raise OAuthTokenError(
                    f"Token refresh failed: {response.status_code}",
                    code=error_data.get("error"),
                    description=error_data.get("error_description"),
                )
            
            token_data = response.json()
            return OAuthTokens(
                access_token=token_data["access_token"],
                token_type=token_data.get("token_type", "Bearer"),
                expires_in=token_data.get("expires_in", 3600),
                refresh_token=token_data.get("refresh_token", refresh_token),
                id_token=token_data.get("id_token"),
                scope=token_data.get("scope"),
            )
            
        except httpx.HTTPError as e:
            raise OAuthTokenError(f"Token refresh request failed: {e}")
    
    async def get_user_info(self, access_token: str) -> OAuthUser:
        """
        Get user information from userinfo endpoint.
        
        Args:
            access_token: Valid access token
        
        Returns:
            OAuthUser with user information
        """
        discovery = await self.discover()
        
        if not discovery.userinfo_endpoint:
            raise OAuthError("Userinfo endpoint not available")
        
        try:
            response = await self.http.get(
                discovery.userinfo_endpoint,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            
            if not response.is_success:
                raise OAuthError(f"Userinfo request failed: {response.status_code}")
            
            data = response.json()
            return OAuthUser.from_dict(data)
            
        except httpx.HTTPError as e:
            raise OAuthError(f"Userinfo request failed: {e}")
    
    async def introspect_token(self, token: str) -> Dict[str, Any]:
        """
        Introspect a token to check validity.
        
        Args:
            token: Token to introspect
        
        Returns:
            Introspection response dict
        """
        discovery = await self.discover()
        
        if not discovery.introspection_endpoint:
            raise OAuthError("Introspection endpoint not available")
        
        data = {"token": token}
        
        # Client authentication
        if self.client_secret:
            auth = (self.client_id, self.client_secret)
        else:
            data["client_id"] = self.client_id
            auth = None
        
        try:
            response = await self.http.post(
                discovery.introspection_endpoint,
                data=data,
                auth=auth,
            )
            return response.json()
            
        except httpx.HTTPError as e:
            raise OAuthError(f"Introspection failed: {e}")
    
    async def revoke_token(self, token: str, token_type_hint: str = "refresh_token") -> bool:
        """
        Revoke a token.
        
        Args:
            token: Token to revoke
            token_type_hint: "access_token" or "refresh_token"
        
        Returns:
            True if successful
        """
        discovery = await self.discover()
        
        if not discovery.revocation_endpoint:
            raise OAuthError("Revocation endpoint not available")
        
        data = {
            "token": token,
            "token_type_hint": token_type_hint,
        }
        
        if self.client_secret:
            auth = (self.client_id, self.client_secret)
        else:
            data["client_id"] = self.client_id
            auth = None
        
        try:
            response = await self.http.post(
                discovery.revocation_endpoint,
                data=data,
                auth=auth,
            )
            return response.is_success
            
        except httpx.HTTPError as e:
            raise OAuthError(f"Revocation failed: {e}")
    
    def get_logout_url(self, id_token: Optional[str] = None, post_logout_redirect: Optional[str] = None) -> str:
        """
        Get logout URL for end session.
        
        Args:
            id_token: ID token hint for logout
            post_logout_redirect: URL to redirect after logout
        
        Returns:
            Logout URL
        """
        params = {}
        
        if id_token:
            params["id_token_hint"] = id_token
        
        if post_logout_redirect:
            params["post_logout_redirect_uri"] = post_logout_redirect
        
        params["client_id"] = self.client_id
        
        # Use discovery or default
        endpoint = f"{self.auth_server}/api/auth/sign-out"
        if self._discovery and self._discovery.end_session_endpoint:
            endpoint = self._discovery.end_session_endpoint
        
        if params:
            return f"{endpoint}?{urlencode(params)}"
        return endpoint
