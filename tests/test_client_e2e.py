#!/usr/bin/env python3
import asyncio, sys, tempfile
from pathlib import Path
from typing import Dict, Any

# Local imports
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mcp_client import MCPClientManager, Config  # noqa: E402

def stdio_cfg(py: str, entry: str, args: list[str] = [], cwd: str | None = None) -> Dict[str, Any]:
    return {"connection_type": "stdio", "command": py, "args": [entry, *args], "cwd": cwd, "env": {}}

async def main() -> int:
    py = sys.executable or "python3"
    repo = Path(__file__).resolve().parents[1]

    s2 = str(repo / "s2.py")
    term = str(repo / "terminal2.py")

    with tempfile.TemporaryDirectory(prefix="mcp_fs_") as ws:
        ws_path = Path(ws)
        (ws_path / "alpha.txt").write_text("hello alpha\n", encoding="utf-8")
        (ws_path / "nested").mkdir(parents=True, exist_ok=True)
        (ws_path / "nested" / "beta.txt").write_text("beta content\n", encoding="utf-8")

        cfg = Config(mcp_servers={
            "fs": stdio_cfg(py, s2, [str(ws_path)], cwd=str(repo)),
            "term": stdio_cfg(py, term, cwd=str(repo)),
        })

        async with MCPClientManager(cfg) as mgr:
            print("-- Capabilities --")
            print(await mgr.list_formatted_capabilities())

            caps = mgr.get_capabilities()
            tools = caps["tools"]; resources = caps["resources"]; prompts = caps["prompts"]

            def find(d: Dict[str, Any], suffix: str) -> str:
                if suffix in d: return suffix
                for k in d.keys():
                    if k.endswith(suffix): return k
                # bare-name fallback
                suf = suffix.lstrip(".")
                if suf in d: return suf
                raise KeyError(f"Missing {suffix}; have: {list(d.keys())[:10]}")

            list_dir = find(tools, ".list_directory")
            write_file = find(tools, ".write_file")
            read_file = find(tools, ".read_file")
            edit_file = find(tools, ".edit_file")
            search_files = find(tools, ".search_files")
            tree = find(tools, ".directory_tree")
            run_cmd = find(tools, ".run_command")
            term_status = find(resources, ".get_terminal_status")
            term_prompt = find(prompts, ".execute_terminal_command")

            def ok(label: str, cond: bool):
                print(("[PASS] " if cond else "[FAIL] ") + label)
                return cond

            # 1) list directory
            out = await mgr.execute_action({"action_type":"tool","action_name":list_dir,"arguments":{"path":str(ws_path)}})
            ok("fs.list_directory", isinstance(out, str) and out.strip() != "" and not out.lower().startswith("error"))

            # 2) write + read
            newp = ws_path / "gamma.txt"
            w = await mgr.execute_action({"action_type":"tool","action_name":write_file,"arguments":{"path":str(newp),"content":"gamma!\n"}})
            r = await mgr.execute_action({"action_type":"tool","action_name":read_file,"arguments":{"path":str(newp)}})
            ok("fs.write_file+read_file", isinstance(w, str) and isinstance(r, str) and r.strip() != "" and not r.lower().startswith("error"))

            # 3) edit (dry_run default True on your server)
            e = await mgr.execute_action({"action_type":"tool","action_name":edit_file,
                                          "arguments":{"path":str(newp),"edits":[{"oldText":"gamma!","newText":"delta!"}]}})
            ok("fs.edit_file (dry_run)", isinstance(e, str) and e.strip() != "" and not e.lower().startswith("error"))

            # 4) search with exclude
            s = await mgr.execute_action({"action_type":"tool","action_name":search_files,
                                          "arguments":{"path":str(ws_path),"pattern":"txt","exclude_patterns":[r"nested/.*"]}})
            ok("fs.search_files exclude", isinstance(s, str) and s.strip() != "" and not s.lower().startswith("error"))

            # 5) directory tree
            t = await mgr.execute_action({"action_type":"tool","action_name":tree,"arguments":{"path":str(ws_path)}})
            ok("fs.directory_tree", isinstance(t, str) and t.strip() != "" and not t.lower().startswith("error"))

            # 6) terminal resource + prompt + tool
            rs = await mgr.execute_action({"action_type":"resource","action_name":term_status,"arguments":{}})
            ok("term.get_terminal_status", isinstance(rs, str) and rs.strip() != "" and not rs.lower().startswith("error"))

            pr = await mgr.execute_action({"action_type":"prompt","action_name":term_prompt,"arguments":{"command":"echo hello_mcp"}})
            ok("term.prompt execute", isinstance(pr, str) and pr.strip() != "" and not pr.lower().startswith("error"))

            rc = await mgr.execute_action({"action_type":"tool","action_name":run_cmd,"arguments":{"command":"echo hi_from_terminal","directory":"~","timeout":5.0}})
            ok("term.run_command", isinstance(rc, str) and "hi_from_terminal" in rc)

            # 7) denylist check
            dn = await mgr.execute_action({"action_type":"tool","action_name":run_cmd,"arguments":{"command":"rm -rf /","directory":"~","timeout":2.0}})
            ok("term.run_command denylist", isinstance(dn, str) and "forbidden" in dn.lower())

    return 0

if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
