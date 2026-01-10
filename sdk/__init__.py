"""
MCP Machine Identity Fabric & OAuth 2.1 SDK - Python

Two SDKs in one package:

1. MCP Machine Identity (M2M)
   - For AI agents and backend services
   - Uses client_credentials grant
   - See: mcp_identity.py, e2e_demo.py

2. OAuth User Authentication  
   - For user-facing OAuth 2.1 flows
   - Uses authorization_code grant with PKCE
   - See: oauth_client.py, oauth_demo.py
"""

from .mcp_identity import (
    # Agent Client
    MCPAgentClient,
    
    # Resource Server
    MCPResourceServer,
    
    # Admin Client
    MCPAdminClient,
    
    # Data Classes
    MCPCredentials,
    MCPToken,
    ValidationResult,
    ClientStatus,
    
    # Exceptions
    MCPError,
    MCPRegistrationError,
    MCPAuthError,
    MCPValidationError,
    MCPRateLimitError,
    
    # FastAPI Integration
    create_mcp_dependency,
    
    # Convenience Functions
    register_agent,
    get_access_token,
)

from .oauth_client import (
    # OAuth Client
    OAuthClient,
    
    # Data Classes
    OAuthTokens,
    OAuthUser,
    OAuthDiscovery,
    
    # Exceptions
    OAuthError,
    OAuthAuthorizationError,
    OAuthTokenError,
    OAuthSessionError,
    
    # PKCE Helpers
    generate_pkce_pair,
    generate_state,
)

__version__ = "0.2.0"

__all__ = [
    # === MCP Machine Identity ===
    # Agent Client
    "MCPAgentClient",
    
    # Resource Server
    "MCPResourceServer",
    
    # Admin Client
    "MCPAdminClient",
    
    # Data Classes
    "MCPCredentials",
    "MCPToken",
    "ValidationResult",
    "ClientStatus",
    
    # Exceptions
    "MCPError",
    "MCPRegistrationError",
    "MCPAuthError",
    "MCPValidationError",
    "MCPRateLimitError",
    
    # FastAPI Integration
    "create_mcp_dependency",
    
    # Convenience Functions
    "register_agent",
    "get_access_token",
    
    # === OAuth User Authentication ===
    # OAuth Client
    "OAuthClient",
    
    # Data Classes
    "OAuthTokens",
    "OAuthUser",
    "OAuthDiscovery",
    
    # Exceptions
    "OAuthError",
    "OAuthAuthorizationError",
    "OAuthTokenError",
    "OAuthSessionError",
    
    # PKCE Helpers
    "generate_pkce_pair",
    "generate_state",
    
    # Version
    "__version__",
]

