"""
CLI entry point for A/MCL server.

Provides setup, start, and status commands.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import click

from amcl.storage.database import AMCL_DATA_DIR, DB_PATH


@click.group()
@click.version_option(version="1.0.0", prog_name="amcl-server")
def main():
    """A/MCL — Agent/Multi-Coding-agent Context Layer.

    MCP server for automatic context persistence across AI coding agents.
    Install once, and every MCP-compatible agent auto-discovers shared context.
    """
    pass


@main.command()
def setup():
    """Initialize A/MCL data directory and database."""
    click.echo("🔧 Setting up A/MCL...")

    # Create data directory
    AMCL_DATA_DIR.mkdir(parents=True, exist_ok=True)
    click.echo(f"   ✅ Data directory: {AMCL_DATA_DIR}")

    # Initialize database
    from amcl.storage.database import get_connection

    conn = get_connection()
    conn.close()
    click.echo(f"   ✅ Database: {DB_PATH}")

    # Find the amcl-server script path for MCP config
    script_path = _find_script_path()

    # Generate MCP config snippet
    mcp_config = {
        "amcl": {
            "command": script_path,
            "args": ["start"],
            "env": {
                "AMCL_DATA_DIR": str(AMCL_DATA_DIR),
                "AMCL_LOG_LEVEL": "info",
            },
        }
    }

    click.echo("")
    click.echo("📋 Add this to your MCP config to enable A/MCL:")
    click.echo("")
    click.echo(json.dumps(mcp_config, indent=2))
    click.echo("")

    # Try to auto-register in all common MCP config locations
    registered = _try_auto_register(mcp_config)
    if registered:
        click.echo("   ✅ Auto-registered in:")
        for r in registered:
            click.echo(f"      - {r}")
    else:
        click.echo("   ℹ️  No agent configs found. Copy the config above to your agent's MCP settings.")

    click.echo("")
    click.echo("🚀 A/MCL is ready! All targeted agents will auto-discover context on next launch.")


@main.command()
def status():
    """Check A/MCL status and database info."""
    click.echo("📊 A/MCL Status")
    click.echo(f"   Data dir:  {AMCL_DATA_DIR}")
    click.echo(f"   Database:  {DB_PATH}")

    if DB_PATH.exists():
        click.echo(f"   DB size:   {DB_PATH.stat().st_size / 1024:.1f} KB")

        from amcl.storage.database import get_connection

        conn = get_connection()
        try:
            projects = conn.execute("SELECT COUNT(*) as c FROM projects").fetchone()
            messages = conn.execute("SELECT COUNT(*) as c FROM messages").fetchone()
            decisions = conn.execute("SELECT COUNT(*) as c FROM decisions").fetchone()
            sessions = conn.execute("SELECT COUNT(*) as c FROM agent_sessions").fetchone()

            click.echo(f"   Projects:  {projects['c']}")
            click.echo(f"   Messages:  {messages['c']}")
            click.echo(f"   Decisions: {decisions['c']}")
            click.echo(f"   Sessions:  {sessions['c']}")
        finally:
            conn.close()

        click.echo("   Status:    ✅ Ready")
    else:
        click.echo("   Status:    ❌ Not initialized (run `amcl-server setup`)")


@main.command()
def check():
    """Check if A/MCL is configured in detected AI agents."""
    click.echo("🔍 Checking A/MCL integrations...")
    
    home = Path.home()
    config_locations = {
        "Claude Desktop": [
            home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json",
            home / ".config" / "claude" / "claude_desktop_config.json",
        ],
        "Antigravity": [home / ".gemini" / "antigravity" / "mcp_config.json"],
        "Cursor": [home / ".cursor" / "mcp.json"],
        "Amp": [home / ".config" / "amp" / "settings.json"],
        "Generic MCP": [home / ".mcp" / "config.json"],
        "Roo / Cline (VSCode)": [home / "Library" / "Application Support" / "Code" / "User" / "globalStorage" / "rooveterinaryinc.roo-cline" / "settings" / "cline_mcp_settings.json"],
        "Roo / Cline (Cursor)": [home / "Library" / "Application Support" / "Cursor" / "User" / "globalStorage" / "rooveterinaryinc.roo-cline" / "settings" / "cline_mcp_settings.json"],
    }

    found_any = False
    for agent_name, paths in config_locations.items():
        for config_path in paths:
            if not config_path.exists():
                continue
            
            found_any = True
            try:
                content = config_path.read_text()
                existing = json.loads(content) if content.strip() else {}
                
                is_configured = False
                if config_path.name == "settings.json" and "amp" in str(config_path):
                    if "dummy-test" in existing.get("amp.mcpServers", {}) or "amcl" in existing.get("amp.mcpServers", {}):
                        is_configured = True
                elif "amcl" in existing.get("mcpServers", {}):
                    is_configured = True
                elif "amcl" in existing.get("servers", {}):
                    is_configured = True
                
                if is_configured:
                    click.echo(f"   ✅ {agent_name}: Configured ({config_path})")
                else:
                    click.echo(f"   ❌ {agent_name}: Installed, but A/MCL is NOT configured ({config_path})")
            except Exception:
                click.echo(f"   ⚠️  {agent_name}: Error reading config ({config_path})")

    if not found_any:
        click.echo("   ℹ️  No supported AI agents detected on this system.")
    
    click.echo("")
    click.echo("Run `amcl-server setup` to automatically fix any missing configurations.")


@main.command()
def start():
    """Start the MCP server on stdio (used by agents, not typically run manually)."""
    from amcl.mcp.server import run_server

    run_server()


# ── Helpers ──────────────────────────────────────────────────────────

def _find_script_path() -> str:
    """Find the amcl-server executable path."""
    # Check common locations
    for path in [
        Path(sys.prefix) / "bin" / "amcl-server",
        Path(sys.prefix) / "Scripts" / "amcl-server",
        Path(os.path.expanduser("~/.local/bin/amcl-server")),
    ]:
        if path.exists():
            return str(path)
    return "amcl-server"


def _try_auto_register(config: dict) -> list[str]:
    """Try to add A/MCL to all known MCP config locations."""
    home = Path.home()
    config_locations = {
        "Claude Desktop": [
            home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json",
            home / ".config" / "claude" / "claude_desktop_config.json",
        ],
        "Antigravity": [home / ".gemini" / "antigravity" / "mcp_config.json"],
        "Cursor": [home / ".cursor" / "mcp.json"],
        "Amp": [home / ".config" / "amp" / "settings.json"],
        "Generic MCP": [home / ".mcp" / "config.json"],
        "Roo / Cline (VSCode)": [home / "Library" / "Application Support" / "Code" / "User" / "globalStorage" / "rooveterinaryinc.roo-cline" / "settings" / "cline_mcp_settings.json"],
        "Roo / Cline (Cursor)": [home / "Library" / "Application Support" / "Cursor" / "User" / "globalStorage" / "rooveterinaryinc.roo-cline" / "settings" / "cline_mcp_settings.json"],
    }

    registered = []

    for agent_name, paths in config_locations.items():
        for config_path in paths:
            # If the config file doesn't exist but its parent dir does, we can create it
            if not config_path.exists():
                if config_path.parent.exists():
                    try:
                        if config_path.name == "settings.json" and config_path.parent.name == "amp":
                            config_path.write_text(json.dumps({"amp.mcpServers": {}}, indent=2))
                        else:
                            config_path.write_text(json.dumps({"mcpServers": {}}, indent=2))
                    except OSError:
                        continue
                else:
                    continue

            try:
                content = config_path.read_text()
                existing = json.loads(content) if content.strip() else {}

                modified = False
                # Standard mcpServers mapping used by most tools
                if config_path.name == "settings.json" and "amp" in str(config_path):
                    if "amp.mcpServers" not in existing:
                        existing["amp.mcpServers"] = {}
                    existing["amp.mcpServers"].update(config)
                    modified = True
                elif "mcpServers" in existing or config_path.name in ("mcp.json", "claude_desktop_config.json", "cline_mcp_settings.json", "config.json", "mcp_config.json"):
                    if "mcpServers" not in existing:
                        existing["mcpServers"] = {}
                    existing["mcpServers"].update(config)
                    modified = True
                elif "servers" in existing:
                    existing["servers"].update(config)
                    modified = True

                if modified:
                    config_path.write_text(json.dumps(existing, indent=2))
                    registered.append(f"{agent_name} ({config_path})")
            except (json.JSONDecodeError, OSError):
                continue

    return registered


if __name__ == "__main__":
    main()
