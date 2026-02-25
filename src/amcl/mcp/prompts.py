"""
MCP Prompts — pre-built prompt templates for automatic context injection.

Implements 4 prompts from the PRD.

Note: FastMCP prompt handlers do NOT receive a Context object.
Prompts rely on ensure_project() having been called by a tool first,
or fall back gracefully with a no-Context init.
"""

from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP

from amcl.context.context_manager import ContextManager


def register_prompts(mcp: FastMCP, ctx_mgr: ContextManager) -> None:
    """Register all A/MCL prompts on the given FastMCP server."""

    @mcp.prompt(title="Project Context")
    async def project_context() -> str:
        """Inject complete project overview and current state.

        Use this prompt when starting a new session or when the agent
        needs full awareness of the project, conversation history,
        active tasks, and key decisions.
        """
        await ctx_mgr.ensure_project()
        context = ctx_mgr.get_current_context()
        project = context.get("project", {})
        conversation = context.get("conversation", {})
        state = context.get("state", {})
        reasoning = context.get("reasoning", {})
        agents = context.get("agents", {})

        lines = [
            "# Project Context — A/MCL",
            "",
            f"**Project:** {project.get('name', 'Unknown')}",
            f"**Path:** {project.get('path', '')}",
            f"**Language:** {project.get('language', '')}",
            f"**Framework:** {project.get('framework', '')}",
            f"**Git:** {project.get('git', {}).get('branch', '')} @ {project.get('git', {}).get('commit', '')}",
            "",
            "## Conversation Summary",
            conversation.get("summary", "No conversation history."),
            "",
            "## Current Tasks",
        ]

        tasks = state.get("tasks", [])
        if tasks:
            for t in tasks:
                status_icon = {"completed": "✅", "in_progress": "🔄", "pending": "⬜", "blocked": "🚫"}.get(t.get("status", ""), "⬜")
                lines.append(f"  {status_icon} {t.get('description', '')}")
        else:
            lines.append("  No tasks tracked yet.")

        decisions = reasoning.get("decisions", [])
        if decisions:
            lines.append("")
            lines.append("## Key Decisions")
            for d in decisions[-5:]:  # last 5
                lines.append(f"  - **{d.get('question', '')}** → {d.get('answer', '')} ({d.get('agent', '')})")

        agent_history = agents.get("history", [])
        if agent_history:
            lines.append("")
            lines.append("## Agent History")
            for a in agent_history:
                status = "active" if not a.get("ended") else "ended"
                lines.append(f"  - {a.get('agent', '')} ({status})")

        return "\n".join(lines)

    @mcp.prompt(title="Recent Work")
    async def recent_work() -> str:
        """Summarize work done in the last session.

        Provides a concise overview of recent conversation exchanges,
        file changes, and completed tasks.
        """
        await ctx_mgr.ensure_project()
        context = ctx_mgr.get_current_context(include=["conversation", "files", "tasks"])
        conversation = context.get("conversation", {})
        files = context.get("files", {})
        state = context.get("state", {})

        lines = [
            "# Recent Work Summary — A/MCL",
            "",
            "## Conversation",
            conversation.get("summary", "No recent conversation."),
            "",
            "## Files Changed",
        ]

        recent = files.get("recent_changes", [])
        if recent:
            for f in recent[-10:]:
                lines.append(f"  - [{f.get('action', '')}] {f.get('file', '')} — {f.get('summary', '')}")
        else:
            lines.append("  No file changes recorded.")

        completed = [t for t in state.get("tasks", []) if t.get("status") == "completed"]
        if completed:
            lines.append("")
            lines.append("## Completed Tasks")
            for t in completed:
                lines.append(f"  ✅ {t.get('description', '')}")

        return "\n".join(lines)

    @mcp.prompt(title="Continuation")
    async def continuation() -> str:
        """Pick up where the last agent left off.

        Provides context about what was being worked on, what's next,
        and any blockers — so the new agent can continue seamlessly.
        """
        await ctx_mgr.ensure_project()
        context = ctx_mgr.get_current_context()
        project = context.get("project", {})
        conversation = context.get("conversation", {})
        state = context.get("state", {})
        agents = context.get("agents", {})

        lines = [
            "# Continue Where We Left Off — A/MCL",
            "",
            f"You are continuing work on **{project.get('name', '')}**.",
            "",
        ]

        # Who was the previous agent?
        history = agents.get("history", [])
        if len(history) >= 2:
            prev = history[-2]
            lines.append(f"The previous agent was **{prev.get('agent', '')}** "
                         f"(switched because: {prev.get('reason_for_switch', 'unknown')}).")
            lines.append("")

        # What was the conversation about?
        lines.append("## What Was Being Discussed")
        lines.append(conversation.get("summary", "No conversation summary available."))
        lines.append("")

        # What's next?
        in_progress = [t for t in state.get("tasks", []) if t.get("status") == "in_progress"]
        pending = [t for t in state.get("tasks", []) if t.get("status") == "pending"]
        blocked = [t for t in state.get("tasks", []) if t.get("status") == "blocked"]

        if in_progress:
            lines.append("## Currently In Progress")
            for t in in_progress:
                lines.append(f"  🔄 {t.get('description', '')}")
            lines.append("")

        if blocked:
            lines.append("## ⚠️ Blockers")
            for t in blocked:
                lines.append(f"  🚫 {t.get('description', '')}")
            lines.append("")

        if pending:
            lines.append("## Up Next")
            for t in pending[:5]:
                lines.append(f"  ⬜ {t.get('description', '')}")

        return "\n".join(lines)

    @mcp.prompt(title="Decisions Log")
    async def decisions_log() -> str:
        """Inject key decisions and their rationale.

        Lists all design decisions made during the project, including
        alternatives considered and which agent made each decision.
        """
        await ctx_mgr.ensure_project()
        decisions = ctx_mgr.get_reasoning()

        if not decisions:
            return "# Decisions Log — A/MCL\n\nNo decisions logged yet."

        lines = ["# Decisions Log — A/MCL", ""]
        for i, d in enumerate(decisions, 1):
            lines.append(f"## Decision {i}: {d.get('question', '')}")
            lines.append(f"**Answer:** {d.get('answer', '')}")
            lines.append(f"**Reasoning:** {d.get('reasoning', '')}")
            alts = d.get("alternatives", [])
            if alts:
                lines.append(f"**Alternatives:** {', '.join(alts)}")
            lines.append(f"**Agent:** {d.get('agent', '')} | **Time:** {d.get('timestamp', '')}")
            lines.append("")

        return "\n".join(lines)
