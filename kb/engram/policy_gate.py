# kb/engram/policy_gate.py
"""
Policy Gate - The GCM Security Layer for Engram Access

This implements Gate 2 from the GCM architecture:
- Controls which nodes/concepts the RLM (Agent) can access
- Enforces identity-based permissions
- Logs all access for audit

The Policy Gate sits between the Navigator and the Sandbox:

    ┌─────────────┐         ┌─────────────┐         ┌─────────────┐
    │   Sandbox   │ ──req─→ │ Policy Gate │ ──if ok─→ │  Navigator  │
    │   (RLM)     │ ←─res── │   (GCM)     │ ←─data── │  (Engram)   │
    └─────────────┘         └─────────────┘         └─────────────┘
                                  │
                                  ▼
                            ┌─────────────┐
                            │  Audit Log  │
                            └─────────────┘

Access Control Model:
- Nodes have "resource URIs": tools:fs.read, skills:auth.login, docs:api.md
- Agents have "roles" with "permissions": mcp:admin, user:read, user:write
- The Gate matches permissions against resource URIs
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set
import fnmatch
import json

from config import get_logger

logger = get_logger("engram.policy_gate")


class AccessDecision(Enum):
    """The result of a policy check."""
    ALLOW = "allow"
    DENY = "deny"
    AUDIT = "audit"  # Allow but log for review


@dataclass
class AccessRequest:
    """A request to access an Engram resource."""
    resource_uri: str          # e.g., "tools:fs.read", "nodes:12345"
    action: str                # "read", "write", "execute", "traverse"
    requester_id: str          # Agent/Session ID
    requester_roles: List[str] # ["mcp:admin", "user:read"]
    org_id: Optional[str] = None
    mission_id: Optional[str] = None
    context: Dict[str, Any] = field(default_factory=dict)


@dataclass  
class AccessResult:
    """The result of an access check."""
    decision: AccessDecision
    resource_uri: str
    reason: str
    matched_rule: Optional[str] = None
    audit_id: Optional[str] = None


@dataclass
class PolicyRule:
    """A single policy rule."""
    id: str
    pattern: str           # Glob pattern: "tools:*", "skills:auth.*"
    actions: List[str]     # ["read", "execute"] or ["*"]
    roles: List[str]       # Required roles: ["mcp:admin"] or ["*"]
    decision: AccessDecision
    priority: int = 0      # Higher = checked first
    
    def matches(self, request: AccessRequest) -> bool:
        """Check if this rule matches the request."""
        # Check resource pattern
        if not fnmatch.fnmatch(request.resource_uri, self.pattern):
            return False
            
        # Check action
        if "*" not in self.actions and request.action not in self.actions:
            return False
            
        # Check roles
        if "*" not in self.roles:
            if not any(role in self.roles for role in request.requester_roles):
                return False
                
        return True


class PolicyGate:
    """
    The GCM Policy Gate for Engram access control.
    
    Implements a role-based access control (RBAC) model with:
    - Pattern-based resource matching
    - Hierarchical role inheritance
    - Audit logging
    
    Default Policy (when no rules match):
    - DENY all access (fail-closed)
    """
    
    # Default rules (can be extended via config)
    DEFAULT_RULES = [
        # Admin can do anything
        PolicyRule(
            id="admin_all",
            pattern="*",
            actions=["*"],
            roles=["mcp:admin"],
            decision=AccessDecision.ALLOW,
            priority=1000
        ),
        # Users can read docs
        PolicyRule(
            id="user_read_docs",
            pattern="docs:*",
            actions=["read", "traverse"],
            roles=["user:read", "user:write"],
            decision=AccessDecision.ALLOW,
            priority=100
        ),
        # Users can read tools metadata (not execute)
        PolicyRule(
            id="user_read_tools",
            pattern="tools:*",
            actions=["read", "traverse"],
            roles=["user:read", "user:write"],
            decision=AccessDecision.ALLOW,
            priority=100
        ),
        # Users can execute safe tools
        PolicyRule(
            id="user_exec_safe",
            pattern="tools:filesystem.read*",
            actions=["execute"],
            roles=["user:write"],
            decision=AccessDecision.ALLOW,
            priority=150
        ),
        # Users can read/execute skills they own
        PolicyRule(
            id="user_skills",
            pattern="skills:*",
            actions=["read", "execute", "traverse"],
            roles=["user:write"],
            decision=AccessDecision.ALLOW,
            priority=100
        ),
        # Audit all node content access
        PolicyRule(
            id="audit_content",
            pattern="nodes:*",
            actions=["read"],
            roles=["*"],
            decision=AccessDecision.AUDIT,
            priority=50
        ),
    ]
    
    def __init__(
        self,
        rules: Optional[List[PolicyRule]] = None,
        default_decision: AccessDecision = AccessDecision.DENY,
        audit_callback: Optional[callable] = None
    ):
        self.rules = sorted(
            rules or self.DEFAULT_RULES,
            key=lambda r: r.priority,
            reverse=True
        )
        self.default_decision = default_decision
        self.audit_callback = audit_callback
        self._audit_log: List[Dict[str, Any]] = []
        
    def check(self, request: AccessRequest) -> AccessResult:
        """
        Check if an access request is allowed.
        
        Evaluates rules in priority order, returns first match.
        If no rules match, applies default_decision.
        """
        for rule in self.rules:
            if rule.matches(request):
                result = AccessResult(
                    decision=rule.decision,
                    resource_uri=request.resource_uri,
                    reason=f"Matched rule: {rule.id}",
                    matched_rule=rule.id
                )
                
                # Log the decision
                self._log_access(request, result)
                
                return result
        
        # No rules matched - apply default
        result = AccessResult(
            decision=self.default_decision,
            resource_uri=request.resource_uri,
            reason="No matching rules - default policy applied"
        )
        self._log_access(request, result)
        return result
    
    def check_batch(
        self, 
        requests: List[AccessRequest]
    ) -> Dict[str, AccessResult]:
        """Check multiple resources at once."""
        return {req.resource_uri: self.check(req) for req in requests}
    
    def filter_allowed(
        self,
        resource_uris: List[str],
        requester_id: str,
        roles: List[str],
        action: str = "read"
    ) -> List[str]:
        """
        Filter a list of resources to only those allowed.
        
        Useful for filtering search results before returning to agent.
        """
        allowed = []
        for uri in resource_uris:
            request = AccessRequest(
                resource_uri=uri,
                action=action,
                requester_id=requester_id,
                requester_roles=roles
            )
            result = self.check(request)
            if result.decision in (AccessDecision.ALLOW, AccessDecision.AUDIT):
                allowed.append(uri)
        return allowed
    
    def _log_access(self, request: AccessRequest, result: AccessResult):
        """Log an access decision."""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "resource": request.resource_uri,
            "action": request.action,
            "requester": request.requester_id,
            "roles": request.requester_roles,
            "decision": result.decision.value,
            "reason": result.reason,
            "rule": result.matched_rule,
            "mission_id": request.mission_id,
        }
        
        self._audit_log.append(entry)
        
        # Keep log bounded
        if len(self._audit_log) > 10000:
            self._audit_log = self._audit_log[-5000:]
            
        # Call external audit callback if provided
        if self.audit_callback:
            try:
                self.audit_callback(entry)
            except Exception as e:
                logger.warning(f"Audit callback failed: {e}")
                
        # Log denials at warning level
        if result.decision == AccessDecision.DENY:
            logger.warning(f"ACCESS DENIED: {request.requester_id} → {request.resource_uri}")
            
    def get_audit_log(
        self, 
        limit: int = 100,
        filter_decision: Optional[AccessDecision] = None
    ) -> List[Dict[str, Any]]:
        """Get recent audit log entries."""
        entries = self._audit_log
        if filter_decision:
            entries = [e for e in entries if e["decision"] == filter_decision.value]
        return entries[-limit:]
    
    def add_rule(self, rule: PolicyRule):
        """Add a new rule dynamically."""
        self.rules.append(rule)
        self.rules.sort(key=lambda r: r.priority, reverse=True)
        
    def remove_rule(self, rule_id: str):
        """Remove a rule by ID."""
        self.rules = [r for r in self.rules if r.id != rule_id]


class GatedNavigator:
    """
    A Navigator wrapped with Policy Gate enforcement.
    
    This is the actual interface exposed to the RLM (Agent).
    All calls go through the Policy Gate before reaching the Navigator.
    """
    
    def __init__(
        self,
        navigator: "GraphNavigator",
        gate: PolicyGate,
        requester_id: str,
        roles: List[str],
        mission_id: Optional[str] = None
    ):
        self.navigator = navigator
        self.gate = gate
        self.requester_id = requester_id
        self.roles = roles
        self.mission_id = mission_id
        
    def _check(self, uri: str, action: str = "read") -> AccessResult:
        """Internal access check."""
        request = AccessRequest(
            resource_uri=uri,
            action=action,
            requester_id=self.requester_id,
            requester_roles=self.roles,
            mission_id=self.mission_id
        )
        return self.gate.check(request)
    
    async def get_file_structure(self, file_pattern: str, **kwargs):
        """Get file structure (gated)."""
        result = self._check(f"docs:{file_pattern}", "traverse")
        if result.decision == AccessDecision.DENY:
            raise PermissionError(f"Access denied: {result.reason}")
            
        nav_result = await self.navigator.get_file_structure(file_pattern, **kwargs)
        
        # Filter nodes by permission
        allowed_nodes = []
        for node in nav_result.nodes:
            node_uri = f"nodes:{node.id}"
            if self._check(node_uri, "read").decision != AccessDecision.DENY:
                allowed_nodes.append(node)
                
        nav_result.nodes = allowed_nodes
        return nav_result
    
    async def load_content(self, node_ids: List[int], **kwargs):
        """Load content (gated) - this is the expensive operation."""
        allowed_ids = []
        for node_id in node_ids:
            result = self._check(f"nodes:{node_id}", "read")
            if result.decision != AccessDecision.DENY:
                allowed_ids.append(node_id)
                
        if not allowed_ids:
            return {}
            
        return await self.navigator.load_content(allowed_ids, **kwargs)
    
    async def hub_hop(self, source_id: int, **kwargs):
        """Hub-hop navigation (gated)."""
        result = self._check(f"nodes:{source_id}", "traverse")
        if result.decision == AccessDecision.DENY:
            raise PermissionError(f"Access denied: {result.reason}")
            
        return await self.navigator.hub_hop(source_id, **kwargs)
    
    async def concept_search(self, concept_names: List[str], **kwargs):
        """Concept search (gated)."""
        # Concept searches are generally allowed but results filtered
        nav_result = await self.navigator.concept_search(concept_names, **kwargs)
        
        allowed_nodes = []
        for node in nav_result.nodes:
            if self._check(f"nodes:{node.id}", "read").decision != AccessDecision.DENY:
                allowed_nodes.append(node)
                
        nav_result.nodes = allowed_nodes
        return nav_result
    
    async def load_function(self, file_pattern: str, function_name: str):
        """Load a specific function (gated)."""
        # Check both file and function access
        result = self._check(f"docs:{file_pattern}", "read")
        if result.decision == AccessDecision.DENY:
            raise PermissionError(f"Access denied: {result.reason}")
            
        return await self.navigator.load_function(file_pattern, function_name)
