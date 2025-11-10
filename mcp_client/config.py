from __future__ import annotations
import json, os
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field, ValidationError
from dotenv import load_dotenv

class StdioConfig(BaseModel):
    connection_type: str = "stdio"
    command: str
    args: list[str] = Field(default_factory=list)
    cwd: Optional[str] = None
    env: Dict[str, Any] = Field(default_factory=dict)
    disabled: bool = False

class StreamableHttpConfig(BaseModel):
    connection_type: str = "streamable_http"
    url: str
    headers: Dict[str, Any] = Field(default_factory=dict)
    timeout: float = 30.0
    sse_read_timeout: float = 300.0
    terminate_on_close: bool = True
    disabled: bool = False

class SseConfig(BaseModel):
    connection_type: str = "sse"
    url: str
    headers: Dict[str, Any] = Field(default_factory=dict)
    timeout: Optional[float] = None
    sse_read_timeout: Optional[float] = None
    disabled: bool = False

def parse_server_config(data: Dict[str, Any]) -> BaseModel:
    typ = data.get("connection_type", "stdio")
    if typ == "stdio": return StdioConfig(**data)
    if typ == "streamable_http": return StreamableHttpConfig(**data)
    if typ == "sse": return SseConfig(**data)
    raise ValueError(f"Unknown connection_type: {typ}")

class Config(BaseModel):
    mcp_servers: Dict[str, Dict[str, Any]] = Field(default_factory=dict)

    @classmethod
    def load(cls, server_file: str = "mcp_servers.json") -> "Config":
        load_dotenv()
        if not os.path.exists(server_file):
            return cls()
        with open(server_file, "r", encoding="utf-8") as f:
            raw = json.load(f)
        validated: Dict[str, Dict[str, Any]] = {}
        for name, data in raw.items():
            try:
                cfg = parse_server_config(data)
                if not getattr(cfg, "disabled", False):
                    validated[name] = cfg.model_dump()
            except ValidationError:
                # Skip invalid entries; keep loader tolerant
                continue
        return cls(mcp_servers=validated)
