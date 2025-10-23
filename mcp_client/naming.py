from __future__ import annotations

def default_server_prefix(server_key: str, server_info) -> str:
    """
    Prefer server implementation name if present, else the config key.
    Normalize to a short, safe prefix.
    """
    impl = getattr(server_info, "implementation", None)
    impl_name = getattr(impl, "name", None) if impl else None
    base = impl_name or server_key or "server"
    return str(base).strip().replace(" ", "-").lower()
