"""
A/MCL — Agent/Multi-Coding-agent Context Layer.

Run with: python -m amcl
This starts the MCP server on stdio transport.
"""

from amcl.mcp.server import run_server

if __name__ == "__main__":
    run_server()
