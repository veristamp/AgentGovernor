"""Skill discovery demo workflow.

Uses the sandbox socket to search for skills and inspect metadata.
"""
from __future__ import annotations

import skill_discovery


async def main():
    results = await skill_discovery.search("docs")
    if not results:
        return {"error": "no skills found"}

    first = results[0]
    skill_ref = first.get("skillRef", "")
    detail = await skill_discovery.inspect(skill_ref)

    print({"results": results, "detail": detail})

    return {
        "results": results,
        "detail": detail,
    }
