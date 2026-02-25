"""
MCP Server — creates the FastMCP instance and wires up
all tools, resources, and prompts.
"""

from __future__ import annotations

import logging
import os
import signal
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from amcl.context.context_manager import ContextManager
from amcl.mcp.prompts import register_prompts
from amcl.mcp.resources import register_resources
from amcl.mcp.tools import register_tools

logger = logging.getLogger("amcl.server")


def create_server(
    project_dir: str | None = None,
    agent_name: str | None = None,
    db_path: Path | None = None,
) -> tuple[FastMCP, ContextManager]:
    """
    Create and configure the A/MCL MCP server.

    Returns (server, context_manager) so the caller can manage lifecycle.
    """
    # Resolve agent name from env or argument
    _agent = agent_name or os.environ.get("AMCL_AGENT_NAME", "unknown")
    _project = project_dir or os.environ.get("AMCL_PROJECT_DIR")

    # Create context manager
    ctx_mgr = ContextManager(
        db_path=db_path,
        project_dir=_project,
        agent_name=_agent,
    )

    # Create FastMCP server
    mcp = FastMCP(
        "A/MCL Context Server",
        instructions=(
            "A/MCL provides automatic context persistence across AI coding agents. "
            "Use context_get_current to retrieve the full project state including "
            "conversation history, file changes, tasks, and decisions. "
            "Use context_update to save new context as you work. "
            "This enables seamless switching between agents with zero context loss."
        ),
    )

    # Register all components
    register_tools(mcp, ctx_mgr)
    register_resources(mcp, ctx_mgr)
    register_prompts(mcp, ctx_mgr)

    return mcp, ctx_mgr


def run_server() -> None:
    """Entry point: create server and run on stdio transport."""
    logging.basicConfig(
        level=os.environ.get("AMCL_LOG_LEVEL", "WARNING").upper(),
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    mcp, ctx_mgr = create_server()

    def _shutdown(sig, frame):
        logger.info("Shutting down A/MCL server...")
        ctx_mgr.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    logger.info("A/MCL MCP server starting on stdio...")
    mcp.run(transport="stdio")
