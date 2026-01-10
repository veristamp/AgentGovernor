"""
MCP Machine Identity Fabric - Python SDK

A lightweight SDK for MCP agents and resource servers to interact with
the Mono Authz identity fabric.

Usage - Agent Registration & Token Acquisition:
    from mcp_identity import MCPAgentClient
    
    client = MCPAgentClient(
        auth_server="https://auth.example.com",
        reg_jwt="eyJ..."  # Registration invite token
    )
    
    # Register and get credentials
    credentials = await client.register(client_name="my-agent")
    
    # Get access token
    token = await client.get_token(scopes=["read:data"])
    
Usage - Resource Server Validation:
    from mcp_identity import MCPResourceServer
    
    server = MCPResourceServer(
        auth_server="https://auth.example.com",
        my_audience="mcp://rag-service",
        admin_session_cookie="..."  # For client status checks
    )
    
    # Validate incoming token
    result = await server.validate_token(token, required_scopes=["read:data"])
    if result.valid:
        print(f"Client: {result.client_id}, Scopes: {result.scopes}")
"""

import asyncio
import httpx
import hashlib
import base64
import json
import time
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from functools import lru_cache
import logging

logger = logging.getLogger(__name__)

# =============================================================================
# Configuration
# =============================================================================

DEFAULT_TOKEN_TTL = 600  # 10 minutes
CLIENT_CACHE_TTL = 60    # Cache client status for 60 seconds


# =============================================================================
# Exceptions
# =============================================================================

class MCPAuthError(Exception):
    """Base exception for MCP authentication errors."""
    def __init__(self, message: str, code: Optional[str] = None):
        super().__init__(message)
        self.code = code


class MCPRateLimitError(MCPAuthError):
    """
    Raised when token minting rate limit is exceeded.
    
    Attributes:
        retry_after: Seconds to wait before retrying
        remaining: Tokens remaining in the window (0 when limited)
    """
    def __init__(self, message: str, retry_after: int = 60, remaining: int = 0):
        super().__init__(message, code="rate_limit_exceeded")
        self.retry_after = retry_after
        self.remaining = remaining


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class MCPCredentials:
    """Credentials returned after successful registration."""
    client_id: str
    client_secret: str
    allowed_scopes: List[str]
    allowed_audiences: List[str]
    org_id: Optional[str] = None


@dataclass
class MCPToken:
    """Access token with metadata."""
    access_token: str
    token_type: str = "Bearer"
    expires_in: int = 3600
    scope: str = ""
    expires_at: float = field(default_factory=lambda: time.time() + 3600)
    
    @property
    def is_expired(self) -> bool:
        return time.time() >= self.expires_at - 30  # 30s buffer


@dataclass 
class ValidationResult:
    """Result of token validation."""
    valid: bool
    client_id: Optional[str] = None
    org_id: Optional[str] = None
    scopes: List[str] = field(default_factory=list)
    allowed_audiences: List[str] = field(default_factory=list)
    error: Optional[str] = None
    error_code: Optional[str] = None


@dataclass
class ClientStatus:
    """Cached client status for kill switch enforcement."""
    client_id: str
    status: str  # 'active', 'disabled', 'revoked'
    allowed_scopes: List[str]
    allowed_audiences: List[str]
    org_id: Optional[str]
    fetched_at: float
    
    @property
    def is_stale(self) -> bool:
        return time.time() - self.fetched_at > CLIENT_CACHE_TTL


# =============================================================================
# MCP Agent Client
# =============================================================================

class MCPAgentClient:
    """
    Client for MCP agents to register and obtain tokens.
    
    Example:
        client = MCPAgentClient(
            auth_server="https://auth.example.com",
            reg_jwt="eyJ..."
        )
        
        # Register once
        creds = await client.register("my-agent")
        
        # Get tokens as needed
        token = await client.get_token(["read:data"])
    """
    
    def __init__(
        self,
        auth_server: str,
        reg_jwt: Optional[str] = None,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        http_client: Optional[httpx.AsyncClient] = None,
    ):
        """
        Initialize the agent client.
        
        Args:
            auth_server: Base URL of the authorization server
            reg_jwt: Registration invite token (for new registrations)
            client_id: Existing client ID (if already registered)
            client_secret: Existing client secret (if already registered)
            http_client: Optional custom HTTP client
        """
        self.auth_server = auth_server.rstrip('/')
        self.reg_jwt = reg_jwt
        self.client_id = client_id
        self.client_secret = client_secret
        self._http = http_client or httpx.AsyncClient(timeout=30.0)
        self.origin = self.auth_server
        self._current_token: Optional[MCPToken] = None
        self._credentials: Optional[MCPCredentials] = None
    
    async def register(
        self,
        client_name: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> MCPCredentials:
        """
        Register a new MCP machine client.
        
        Args:
            client_name: Human-readable name for this agent
            metadata: Optional metadata to attach
            
        Returns:
            MCPCredentials with client_id and client_secret
            
        Raises:
            MCPRegistrationError: If registration fails
        """
        if not self.reg_jwt:
            raise MCPRegistrationError("Registration requires a REG_JWT invite token")
        
        body = {"client_name": client_name}
        if metadata:
            body["metadata"] = metadata
        
        response = await self._http.post(
            f"{self.auth_server}/api/mcp/register",
            json=body,
            headers={
                "Authorization": f"Bearer {self.reg_jwt}",
                "Content-Type": "application/json",
                "Origin": self.origin,
            },
        )
        
        if response.status_code == 201:
            data = response.json()
            self._credentials = MCPCredentials(
                client_id=data["client_id"],
                client_secret=data["client_secret"],
                allowed_scopes=data.get("allowed_scopes", []),
                allowed_audiences=data.get("allowed_audiences", []),
                org_id=data.get("org_id"),
            )
            self.client_id = self._credentials.client_id
            self.client_secret = self._credentials.client_secret
            
            logger.info(f"Registered MCP client: {self.client_id}")
            return self._credentials
        
        error_data = response.json() if response.content else {}
        raise MCPRegistrationError(
            error_data.get("error_description", f"Registration failed: {response.status_code}"),
            code=error_data.get("error"),
        )
    
    async def get_token(
        self,
        scopes: Optional[List[str]] = None,
        audience: Optional[str] = None,
        force_refresh: bool = False,
    ) -> MCPToken:
        """
        Get an access token, refreshing if necessary.
        
        When an audience is specified, Better Auth issues a JWT access token
        with the 'aud' claim set, enabling stateless validation via JWKS.
        Without audience, an opaque token is issued (requires introspection).
        
        Args:
            scopes: Scopes to request (must be within allowed set)
            audience: Target audience/resource (RFC 8707). If provided, a JWT is issued.
            force_refresh: Force a new token even if current is valid
            
        Returns:
            MCPToken with access token (JWT if audience specified, opaque otherwise)
        """
        if not self.client_id or not self.client_secret:
            raise MCPAuthError("Client credentials not set. Call register() first.")
        
        # Return cached token if still valid
        if not force_refresh and self._current_token and not self._current_token.is_expired:
            return self._current_token
        
        # Request new token
        form_data = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }
        if scopes:
            form_data["scope"] = " ".join(scopes)
        # RFC 8707: Pass audience as 'resource' parameter to get JWT with aud claim
        if audience:
            form_data["resource"] = audience
        
        response = await self._http.post(
            f"{self.auth_server}/api/auth/oauth2/token",
            data=form_data,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin": self.origin,
            },
        )
        
        if response.status_code == 200:
            data = response.json()
            self._current_token = MCPToken(
                access_token=data["access_token"],
                token_type=data.get("token_type", "Bearer"),
                expires_in=data.get("expires_in", 3600),
                scope=data.get("scope", ""),
                expires_at=time.time() + data.get("expires_in", 3600),
            )
            return self._current_token
        
        error_data = response.json() if response.content else {}
        
        # Handle rate limiting (429 Too Many Requests)
        if response.status_code == 429:
            retry_after = error_data.get("retryAfter", 60)
            raise MCPRateLimitError(
                error_data.get("error_description", "Rate limit exceeded"),
                retry_after=retry_after,
            )
        
        raise MCPAuthError(
            error_data.get("error_description", f"Token request failed: {response.status_code}"),
            code=error_data.get("error"),
        )
    
    async def close(self):
        """Close the HTTP client."""
        await self._http.aclose()
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, *args):
        await self.close()


# =============================================================================
# MCP Resource Server
# =============================================================================

class MCPResourceServer:
    """
    Helper for MCP resource servers to validate incoming tokens.
    
    Since Better Auth uses opaque tokens, validation works by:
    1. Checking client status via cached admin API calls
    2. Relying on short TTL for token expiration
    3. Using kill switches (disable/revoke) for immediate invalidation
    
    Example:
        server = MCPResourceServer(
            auth_server="https://auth.example.com",
            my_audience="mcp://rag-service",
        )
        
        result = await server.validate_token(token)
        if result.valid:
            # Token is valid for this audience
            pass
    """
    
    def __init__(
        self,
        auth_server: str,
        my_audience: str,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        admin_api_key: Optional[str] = None,
        admin_session_cookie: Optional[str] = None,
        admin_client: Optional["MCPAdminClient"] = None,
        http_client: Optional[httpx.AsyncClient] = None,
        cache_ttl: int = 60,
    ):
        """
        Initialize the resource server helper.
        
        Args:
            auth_server: Base URL of the authorization server
            my_audience: This resource server's audience identifier
            client_id: Client ID for introspection auth
            client_secret: Client secret for introspection auth
            admin_api_key: API key for admin endpoint access
            admin_session_cookie: Session cookie string for admin access
            admin_client: Pre-authenticated MCPAdminClient
            http_client: Optional custom HTTP client
            cache_ttl: How long to cache client status (seconds)
        """
        self.auth_server = auth_server.rstrip('/')
        self.my_audience = my_audience
        self.client_id = client_id
        self.client_secret = client_secret
        self.admin_api_key = admin_api_key
        self.admin_session_cookie = admin_session_cookie
        self.admin_client = admin_client
        self._http = http_client or httpx.AsyncClient(timeout=30.0)
        self.origin = self.auth_server
        self._client_cache: Dict[str, ClientStatus] = {}
        self.cache_ttl = cache_ttl
        # JWKS caching for JWT validation (stateless)
        self._jwks_cache: Optional[Dict[str, Any]] = None
        self._jwks_fetched_at: float = 0
        self._jwks_cache_ttl: int = 3600  # Cache JWKS for 1 hour
    
    async def validate_token(
        self,
        token: str,
        required_scopes: Optional[List[str]] = None,
        use_jwt: bool = True,
        require_active_check: bool = False,
    ) -> ValidationResult:
        """
        Validate an incoming access token.
        
        Supports two validation modes:
        - **JWT mode** (use_jwt=True): Stateless validation using JWKS.
          Validates signature, expiration, and audience locally.
          No HTTP call to auth server. ~0.1ms latency.
          
        - **Introspection mode** (use_jwt=False): Calls auth server's introspect endpoint.
          Real-time token status check. ~50-100ms latency.
        
        For kill-switch enforcement on high-risk operations, set require_active_check=True
        to verify client status with the auth server even when using JWT mode.
        
        Args:
            token: The Bearer token from Authorization header
            required_scopes: Scopes that must be present in the token
            use_jwt: If True, validate JWT locally using JWKS (default: True)
            require_active_check: If True, call introspect to check real-time status
            
        Returns:
            ValidationResult indicating if token is valid
        """
        if not token:
            return ValidationResult(
                valid=False,
                error="Missing token",
                error_code="missing_token",
            )
        
        try:
            # Determine if token looks like a JWT (has 3 parts separated by dots)
            is_jwt_token = len(token.split('.')) == 3
            
            if use_jwt and is_jwt_token:
                # Fast path: JWT validation locally
                return await self._validate_jwt_token(token, required_scopes, require_active_check)
            else:
                # Slow path: Introspection
                return await self._validate_via_introspect(token, required_scopes)
            
        except Exception as e:
            logger.exception("Token validation error")
            return ValidationResult(
                valid=False,
                error=str(e),
                error_code="validation_error",
            )
    
    async def _validate_jwt_token(
        self,
        token: str,
        required_scopes: Optional[List[str]],
        require_active_check: bool,
    ) -> ValidationResult:
        """
        Validate a JWT access token locally using JWKS.
        
        This is the fast path - no HTTP calls to auth server unless require_active_check=True.
        """
        try:
            # Decode JWT payload (without verification for now - we'll check signature below)
            parts = token.split('.')
            if len(parts) != 3:
                return ValidationResult(
                    valid=False,
                    error="Invalid JWT format",
                    error_code="invalid_token",
                )
            
            # Base64 decode the payload (second part)
            # Add padding if needed
            payload_b64 = parts[1]
            padding = 4 - len(payload_b64) % 4
            if padding != 4:
                payload_b64 += '=' * padding
            
            try:
                payload_json = base64.urlsafe_b64decode(payload_b64)
                payload = json.loads(payload_json)
            except Exception as e:
                return ValidationResult(
                    valid=False,
                    error=f"Failed to decode JWT payload: {e}",
                    error_code="invalid_token",
                )
            
            # Check expiration
            exp = payload.get("exp")
            if exp and time.time() > exp:
                return ValidationResult(
                    valid=False,
                    error="Token has expired",
                    error_code="token_expired",
                )
            
            # Check audience - JWT aud claim should match our audience
            token_aud = payload.get("aud")
            if isinstance(token_aud, list):
                if self.my_audience not in token_aud:
                    return ValidationResult(
                        valid=False,
                        error=f"Token audience {token_aud} does not match {self.my_audience}",
                        error_code="audience_mismatch",
                    )
            elif token_aud != self.my_audience:
                return ValidationResult(
                    valid=False,
                    error=f"Token audience '{token_aud}' does not match '{self.my_audience}'",
                    error_code="audience_mismatch",
                )
            
            # Extract claims
            client_id = payload.get("azp") or payload.get("client_id")
            token_scopes = payload.get("scope", "").split() if isinstance(payload.get("scope"), str) else payload.get("scope", [])
            
            # Check required scopes
            if required_scopes:
                missing = set(required_scopes) - set(token_scopes)
                if missing:
                    return ValidationResult(
                        valid=False,
                        error=f"Missing required scopes: {missing}",
                        error_code="insufficient_scope",
                        client_id=client_id,
                        scopes=token_scopes,
                    )
            
            # Optional: Check client is still active (kill switch)
            # This adds latency but provides real-time revocation checking
            if require_active_check and client_id:
                client = await self._get_client_status(client_id)
                if client and client.status != "active":
                    return ValidationResult(
                        valid=False,
                        error=f"Client is {client.status}",
                        error_code=f"client_{client.status}",
                        client_id=client_id,
                    )
            
            # JWT is valid
            return ValidationResult(
                valid=True,
                client_id=client_id,
                org_id=payload.get("org_id"),
                scopes=token_scopes,
            )
            
        except Exception as e:
            logger.exception("JWT validation error")
            return ValidationResult(
                valid=False,
                error=str(e),
                error_code="jwt_validation_error",
            )
    
    async def _validate_via_introspect(
        self,
        token: str,
        required_scopes: Optional[List[str]],
    ) -> ValidationResult:
        """
        Validate token via auth server introspection.
        
        This is the slow path - requires HTTP call to auth server.
        Use for opaque tokens or when real-time revocation check is needed.
        """
        # Step 1: Call Better Auth's introspect to get client_id
        introspect_result = await self._introspect_token(token)
        
        if not introspect_result.get("active"):
            return ValidationResult(
                valid=False,
                error="Token is inactive or expired",
                error_code="token_inactive",
            )
        
        client_id = introspect_result.get("client_id")
        if not client_id:
            return ValidationResult(
                valid=False,
                error="Token has no client_id",
                error_code="no_client_id",
            )
        
        # Step 2: Get client status (cached)
        client = await self._get_client_status(client_id)
        if not client:
            return ValidationResult(
                valid=False,
                error="Client not found",
                error_code="client_not_found",
                client_id=client_id,
            )
        
        # Step 3: Check kill switches
        if client.status != "active":
            return ValidationResult(
                valid=False,
                error=f"Client is {client.status}",
                error_code=f"client_{client.status}",
                client_id=client_id,
            )
        
        # Step 4: Validate audience
        if self.my_audience not in client.allowed_audiences:
            return ValidationResult(
                valid=False,
                error="Token not valid for this audience",
                error_code="audience_mismatch",
                client_id=client_id,
                allowed_audiences=client.allowed_audiences,
            )
        
        # Step 5: Validate scopes
        token_scopes = introspect_result.get("scope", "").split()
        if required_scopes:
            missing = set(required_scopes) - set(token_scopes)
            if missing:
                return ValidationResult(
                    valid=False,
                    error=f"Missing required scopes: {missing}",
                    error_code="insufficient_scope",
                    client_id=client_id,
                    scopes=token_scopes,
                )
        
        # All checks passed
        return ValidationResult(
            valid=True,
            client_id=client_id,
            org_id=client.org_id,
            scopes=token_scopes,
            allowed_audiences=client.allowed_audiences,
        )
    
    async def _introspect_token(self, token: str) -> Dict[str, Any]:
        """Call Better Auth's introspection endpoint."""
        data = {"token": token}
        if self.client_id and self.client_secret:
            data["client_id"] = self.client_id
            data["client_secret"] = self.client_secret
            
        response = await self._http.post(
            f"{self.auth_server}/api/auth/oauth2/introspect",
            data=data,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin": self.origin,
            },
        )
        
        if response.status_code == 200:
            return response.json()
        
        return {"active": False}
    
    async def _get_client_status(self, client_id: str) -> Optional[ClientStatus]:
        """Get client status, using cache if available."""
        # Check cache
        cached = self._client_cache.get(client_id)
        if cached and not cached.is_stale:
            return cached
        
        # Use admin client if provided
        if self.admin_client:
            response = await self.admin_client.request("GET", f"/api/admin/mcp/clients/{client_id}")
        else:
            # Fallback to direct headers
            headers = {"Origin": self.origin}
            if self.admin_api_key:
                headers["x-api-key"] = self.admin_api_key
            if self.admin_session_cookie:
                headers["Cookie"] = self.admin_session_cookie
            
            response = await self._http.get(
                f"{self.auth_server}/api/admin/mcp/clients/{client_id}",
                headers=headers,
            )
        
        if response.status_code == 200:
            data = response.json()
            client = ClientStatus(
                client_id=client_id,
                status=data.get("status", "active"),
                allowed_scopes=data.get("allowedScopes", []),
                allowed_audiences=data.get("allowedAudiences", []),
                org_id=data.get("orgId"),
                fetched_at=time.time(),
            )
            self._client_cache[client_id] = client
            return client
        
        return None
    
    def clear_cache(self):
        """Clear the client status cache."""
        self._client_cache.clear()
    
    async def close(self):
        """Close the HTTP client."""
        await self._http.aclose()
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, *args):
        await self.close()


# =============================================================================
# MCP Admin Client
# =============================================================================

class MCPAdminClient:
    """
    Client for MCP administrative tasks.
    
    Handles session management, CSRF tokens, and origin headers for
    system-level interactions with the Auth server.
    """
    
    def __init__(
        self,
        auth_server: str,
        http_client: Optional[httpx.AsyncClient] = None,
    ):
        """
        Initialize the admin client.
        
        Args:
            auth_server: Base URL of the authorization server
            http_client: Optional custom HTTP client (must enable cookie support)
        """
        self.auth_server = auth_server.rstrip('/')
        self.origin = self.auth_server
        self.csrf_token: Optional[str] = None
        self._cookies: Dict[str, str] = {}
        self._http = http_client or httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
        )
        
    def _update_cookies(self, response: httpx.Response):
        """Extract and store cookies from the response."""
        for name, value in response.cookies.items():
            self._cookies[name] = value
        
    async def get_csrf_token(self) -> str:
        """Fetch a fresh CSRF token from the server."""
        response = await self._http.get(
            f"{self.auth_server}/api/csrf-token",
            headers={"Origin": self.origin},
            cookies=self._cookies
        )
        self._update_cookies(response)
        data = response.json()
        self.csrf_token = data.get("csrfToken")
        
        # Also check cookies if not in body
        if not self.csrf_token:
            self.csrf_token = self._cookies.get("csrf_token") or self._cookies.get("better-auth.csrf-token")
            
        return self.csrf_token
        
    async def login(self, email: str, password: str) -> bool:
        """
        Sign in as an administrator.
        
        Args:
            email: Admin email
            password: Admin password
            
        Returns:
            True if login successful
        """
        await self.get_csrf_token()
        
        response = await self._http.post(
            f"{self.auth_server}/api/auth/sign-in/email",
            json={"email": email, "password": password},
            headers={
                "X-CSRF-Token": self.csrf_token or "",
                "Origin": self.origin
            },
            cookies=self._cookies
        )
        
        if response.status_code == 200:
            self._update_cookies(response)
            return True
            
        return False
        
    async def request(self, method: str, path: str, **kwargs) -> httpx.Response:
        """
        Make an authenticated request to the admin API.
        
        Automatically handles Origin and X-CSRF-Token for mutation methods.
        """
        if not path.startswith("http"):
            url = f"{self.auth_server}{path}"
        else:
            url = path
            
        headers = kwargs.get("headers", {})
        headers["Origin"] = self.origin
        
        if method.upper() in ["POST", "PUT", "PATCH", "DELETE"] and "/api/auth/oauth2/" not in url:
            if not self.csrf_token:
                await self.get_csrf_token()
            headers["X-CSRF-Token"] = self.csrf_token or ""
            
        kwargs["headers"] = headers
        kwargs["cookies"] = {**self._cookies, **kwargs.get("cookies", {})}
        
        response = await self._http.request(method, url, **kwargs)
        self._update_cookies(response)
        return response
        
    @property
    def session_cookie_string(self) -> str:
        """Get the current session cookies formatted for a Cookie header."""
        return "; ".join([f"{k}={v}" for k, v in self._cookies.items()])
        
    async def close(self):
        """Close the HTTP client."""
        await self._http.aclose()
        
    async def __aenter__(self):
        return self
        
    async def __aexit__(self, *args):
        await self.close()


# =============================================================================
# Exceptions
# =============================================================================

class MCPError(Exception):
    """Base exception for MCP SDK."""
    def __init__(self, message: str, code: Optional[str] = None):
        super().__init__(message)
        self.code = code


class MCPRegistrationError(MCPError):
    """Registration failed."""
    pass


class MCPAuthError(MCPError):
    """Authentication/authorization failed."""
    pass


class MCPValidationError(MCPError):
    """Token validation failed."""
    pass


# =============================================================================
# FastAPI Integration
# =============================================================================

def create_mcp_dependency(
    auth_server: str,
    my_audience: str,
    required_scopes: Optional[List[str]] = None,
    admin_api_key: Optional[str] = None,
):
    """
    Create a FastAPI dependency for MCP token validation.
    
    Usage:
        from fastapi import FastAPI, Depends, HTTPException
        from mcp_identity import create_mcp_dependency
        
        app = FastAPI()
        validate_mcp = create_mcp_dependency(
            auth_server="https://auth.example.com",
            my_audience="mcp://rag-service",
            required_scopes=["read:data"],
        )
        
        @app.get("/query")
        async def query(client=Depends(validate_mcp)):
            return {"client_id": client.client_id}
    """
    from fastapi import Request, HTTPException
    
    server = MCPResourceServer(
        auth_server=auth_server,
        my_audience=my_audience,
        admin_api_key=admin_api_key,
    )
    
    async def dependency(request: Request) -> ValidationResult:
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Missing Bearer token")
        
        token = auth_header[7:]  # Remove "Bearer "
        
        result = await server.validate_token(token, required_scopes)
        
        if not result.valid:
            raise HTTPException(
                status_code=401 if result.error_code == "token_inactive" else 403,
                detail=result.error,
                headers={"WWW-Authenticate": f'Bearer error="{result.error_code}"'},
            )
        
        return result
    
    return dependency


# =============================================================================
# Convenience Functions
# =============================================================================

async def register_agent(
    auth_server: str,
    reg_jwt: str,
    client_name: str,
) -> MCPCredentials:
    """
    One-shot agent registration.
    
    Args:
        auth_server: Authorization server URL
        reg_jwt: Registration invite token
        client_name: Name for this agent
        
    Returns:
        MCPCredentials
    """
    async with MCPAgentClient(auth_server, reg_jwt=reg_jwt) as client:
        return await client.register(client_name)


async def get_access_token(
    auth_server: str,
    client_id: str,
    client_secret: str,
    scopes: Optional[List[str]] = None,
) -> str:
    """
    One-shot token acquisition.
    
    Args:
        auth_server: Authorization server URL
        client_id: Registered client ID
        client_secret: Client secret
        scopes: Scopes to request
        
    Returns:
        Access token string
    """
    async with MCPAgentClient(
        auth_server,
        client_id=client_id,
        client_secret=client_secret,
    ) as client:
        token = await client.get_token(scopes)
        return token.access_token
