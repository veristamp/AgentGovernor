from __future__ import annotations
from typing import Any, Dict, Tuple

class CapabilityIndex:
    """
    Holds fully-qualified capability names and routes them to sessions.
    Keeps small, explicit maps so we don't mutate ClientSessionGroup internals.
    """
    def __init__(self) -> None:
        self.tools: Dict[str, Any] = {}
        self.resources: Dict[str, Any] = {}
        self.prompts: Dict[str, Any] = {}
        self.cap_to_session: Dict[str, Any] = {}
        self.base_to_session: Dict[str, Any] = {}
        self.prefix_to_session: Dict[str, Any] = {}

    def qualify(self, prefix: str, name: str) -> str:
        return f"{prefix}.{name}" if prefix and not name.startswith(prefix + ".") else name

    def register_session(
        self,
        prefix: str,
        session: Any,
        tools: list[Any],
        resources: list[Any],
        prompts: list[Any],
    ) -> None:
        self.prefix_to_session[prefix] = session

        for t in tools:
            q = self.qualify(prefix, t.name)
            self.tools[q] = t
            self.cap_to_session[q] = session
            self.base_to_session[t.name] = session

        for r in resources:
            base = getattr(r, "name", None) or getattr(r, "uri", None) or str(r)
            q = self.qualify(prefix, base)
            self.resources[q] = r
            self.cap_to_session[q] = session
            self.base_to_session[base] = session

        for p in prompts:
            q = self.qualify(prefix, p.name)
            self.prompts[q] = p
            self.cap_to_session[q] = session
            self.base_to_session[p.name] = session

    def resolve_session(self, cap_name: str) -> Any | None:
        # exact → bare → prefix
        s = self.cap_to_session.get(cap_name)
        if s: return s
        s = self.base_to_session.get(cap_name)
        if s: return s
        prefix = cap_name.split(".", 1)[0] if "." in cap_name else ""
        return self.prefix_to_session.get(prefix)

    def all(self) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
        return self.tools, self.resources, self.prompts
