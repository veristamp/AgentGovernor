# test_list_capabilities.py
import asyncio
import argparse
import logging

from mcp_client import Config
from mcp_client import MCPClientManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s :: %(message)s"
)

async def main(server_file: str, output_json: bool) -> int:
    # Load servers (disabled entries are skipped by the loader)
    cfg = Config.load(server_file)

    async with MCPClientManager(cfg) as mgr:
        # Wait until all configured servers are connected (best-effort)
        await mgr.wait_ready()

        if output_json:
            # Raw dict of fully-qualified capabilities
            caps = mgr.get_capabilities()
            # Pretty-print without extra dependencies
            import json
            print(json.dumps({
                "tools": sorted(caps["tools"].keys()),
                "resources": sorted(caps["resources"].keys()),
                "prompts": sorted(caps["prompts"].keys()),
            }, indent=2))
        else:
            # Human-readable listing with arg schemas when available
            text = await mgr.list_formatted_capabilities()
            print(text)

    return 0

if __name__ == "__main__":
    p = argparse.ArgumentParser(description="List MCP capabilities from mcp_servers.json")
    p.add_argument("-f", "--file", default="mcp_servers.json",
                   help="Path to mcp_servers.json (default: ./mcp_servers.json)")
    p.add_argument("--json", action="store_true",
                   help="Print machine-readable JSON of capability names")
    args = p.parse_args()
    raise SystemExit(asyncio.run(main(args.file, args.json)))
