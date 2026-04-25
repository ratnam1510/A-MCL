"""
MCP Resources — read-only data endpoints agents can access.

Implements 7 resources from the PRD using context:// URI scheme.

Note: FastMCP resource handlers do NOT receive a Context object.
Resources rely on ensure_project() having been called by a tool first,
or fall back gracefully with a no-Context init.
"""

from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import FastMCP

from amcl.context.context_manager import ContextManager


def register_resources(mcp: FastMCP, ctx_mgr: ContextManager) -> None:
    """Register all A/MCL resources on the given FastMCP server."""

    @mcp.resource("context://current-project")
    async def current_project() -> str:
        """Complete current project context snapshot."""
        await ctx_mgr.ensure_project()
        context = ctx_mgr.get_current_context()
        return json.dumps(context, indent=2, default=str)

    @mcp.resource("context://conversation")
    async def conversation() -> str:
        """Full conversation history for the current project."""
        await ctx_mgr.ensure_project()
        msgs = ctx_mgr.get_conversation(limit=200)
        return json.dumps({"messages": msgs, "count": len(msgs), "detail": "full"}, indent=2, default=str)

    @mcp.resource("context://files")
    async def files() -> str:
        """File system state and recent changes."""
        await ctx_mgr.ensure_project()
        context = ctx_mgr.get_current_context(include=["files"])
        return json.dumps(context.get("files", {}), indent=2, default=str)

    @mcp.resource("context://reasoning")
    async def reasoning() -> str:
        """Decision log and reasoning chains."""
        await ctx_mgr.ensure_project()
        decisions = ctx_mgr.get_reasoning()
        return json.dumps({"decisions": decisions}, indent=2, default=str)

    @mcp.resource("context://tasks")
    async def tasks() -> str:
        """Active tasks, completed work, and blockers."""
        await ctx_mgr.ensure_project()
        all_tasks = ctx_mgr.get_tasks()
        grouped = {
            "completed": [t for t in all_tasks if t.get("status") == "completed"],
            "in_progress": [t for t in all_tasks if t.get("status") == "in_progress"],
            "pending": [t for t in all_tasks if t.get("status") == "pending"],
            "blocked": [t for t in all_tasks if t.get("status") == "blocked"],
        }
        return json.dumps(grouped, indent=2, default=str)

    @mcp.resource("context://agents")
    async def agents() -> str:
        """History of which agents worked on the project."""
        await ctx_mgr.ensure_project()
        sessions = ctx_mgr.get_agent_history()
        return json.dumps({"history": sessions}, indent=2, default=str)

    @mcp.resource("context://signals")
    async def signals() -> str:
        """Recent deterministic signals extracted from messages."""
        await ctx_mgr.ensure_project()
        recent = ctx_mgr.get_recent_signals()
        return json.dumps(recent, indent=2, default=str)
