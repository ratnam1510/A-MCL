"""
ContextManager — central orchestrator that composes storage,
project detection, conversation logging, and file watching
into a single high-level API.
"""

from __future__ import annotations

import asyncio
import json
import logging
import urllib.parse
from dataclasses import asdict
from pathlib import Path
from typing import Any, Optional

from amcl.context.conversation_logger import ConversationLogger
from amcl.context.file_watcher import FileWatcher
from amcl.context.project_detector import detect_project
from amcl.storage.storage_manager import StorageManager
from amcl.types import ContextSnapshot, GitInfo, ProjectMeta

logger = logging.getLogger("amcl.context_manager")


class ContextManager:
    """
    The brain of A/MCL.

    Holds references to storage, the current project, the conversation
    logger, and the file watcher.  Exposes the high-level methods
    consumed by MCP tools and resources.

    Project initialization is LAZY — it happens on the first tool/resource
    call so that the MCP client's workspace roots can be queried via the
    official ``roots/list`` protocol message.
    """

    def __init__(
        self,
        db_path: Path | None = None,
        project_dir: str | None = None,
        agent_name: str = "unknown",
    ) -> None:
        self._db_path = db_path
        self._forced_project_dir = project_dir
        self._agent_name = agent_name
        self._storage = StorageManager(db_path)

        # These are set lazily by ensure_project()
        self._project_id: int | None = None
        self._project_info: dict | None = None
        self._conversation: ConversationLogger | None = None
        self._watcher: FileWatcher | None = None

        # Concurrency guard for lazy init
        self._init_lock = asyncio.Lock()

    # ── Lazy Initialization ─────────────────────────────────────────

    async def ensure_project(self, ctx: Any = None) -> None:
        """
        Lazily initialize the project context on the first request.

        Tries these resolution strategies in order:
        1. Explicit ``project_dir`` passed to __init__ (or AMCL_PROJECT_DIR env).
        2. ``roots/list`` from the MCP client session (the connected IDE/agent).
        3. ``os.getcwd()`` as a last resort.
        """
        if self._project_id is not None:
            return

        async with self._init_lock:
            # Double-check after acquiring lock
            if self._project_id is not None:
                return

            project_dir = self._forced_project_dir

            # Strategy 2: ask the MCP client for its workspace roots
            if not project_dir and ctx is not None:
                project_dir = await self._resolve_roots_from_client(ctx)

            # Detect project info (language, framework, git, etc.)
            info = detect_project(project_dir)

            logger.info(
                "Project resolved: name=%s path=%s lang=%s",
                info["name"], info["path"], info["language"],
            )

            self._project_id = self._storage.get_or_create_project(
                path=info["path"],
                name=info["name"],
                language=info["language"],
                framework=info["framework"],
                git_branch=info["git_branch"],
                git_commit=info["git_commit"],
            )
            self._project_info = info

            # Sub-components
            self._conversation = ConversationLogger(
                self._storage, self._project_id
            )
            self._watcher = FileWatcher(
                self._storage, self._project_id, info["path"]
            )

            # Start agent session
            self._storage.start_agent_session(
                self._project_id, self._agent_name
            )

            # Start file watcher (safe — skips if path doesn't exist)
            self._watcher.start()

    async def _resolve_roots_from_client(self, ctx: Any) -> str | None:
        """
        Ask the connected MCP client for its workspace roots via the
        official ``roots/list`` protocol message.

        Returns the first root as an absolute filesystem path, or None.
        """
        try:
            session = getattr(ctx, "session", None)
            if session is None:
                return None

            roots_result = await session.list_roots()
            if not roots_result or not roots_result.roots:
                return None

            uri = str(roots_result.roots[0].uri)
            if uri.startswith("file://"):
                decoded = urllib.parse.unquote(uri[len("file://"):])
                logger.info("Resolved workspace root from MCP client: %s", decoded)
                return decoded

        except Exception as e:
            logger.warning("Failed to fetch roots from MCP client: %s", e)

        return None

    # ── Lifecycle ────────────────────────────────────────────────────

    def shutdown(self) -> None:
        """Clean up resources. Safe to call even if never initialized."""
        try:
            if self._watcher:
                self._watcher.stop()
            if self._project_id is not None:
                self._storage.end_agent_session(self._project_id)
            self._storage.close()
        except Exception as e:
            logger.warning("Error during shutdown: %s", e)

    # ── Context Retrieval ────────────────────────────────────────────

    def get_current_context(
        self,
        include: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Return the full context snapshot, optionally filtered by
        sections: conversation, files, tasks, reasoning, agents.
        """
        inc = set(include or ["conversation", "files", "tasks", "reasoning", "agents"])
        result: dict[str, Any] = {}

        # Always include project
        result["project"] = {
            "name": self._project_info["name"],
            "path": self._project_info["path"],
            "language": self._project_info["language"],
            "framework": self._project_info["framework"],
            "git": {
                "branch": self._project_info["git_branch"],
                "commit": self._project_info["git_commit"],
            },
        }

        # Always include global preferences
        result["global_preferences"] = self._storage.get_global_preferences()

        if "conversation" in inc:
            messages = self._conversation.get_recent(limit=50)
            result["conversation"] = {
                "messages": [asdict(m) for m in messages],
                "summary": self._conversation.summarize(),
            }

        if "files" in inc:
            changes = self._storage.get_file_changes(self._project_id)
            # Deduplicate to show only the latest known active files
            active_files = list(
                dict.fromkeys(
                    c.file for c in changes if c.action != "deleted"
                )
            )
            result["files"] = {
                "active": active_files[-20:],  # last 20
                "recent_changes": [asdict(c) for c in changes[-30:]],
            }

        if "tasks" in inc:
            tasks = self._storage.get_tasks(self._project_id)
            result["state"] = {
                "tasks": [asdict(t) for t in tasks],
                "current_goal": self._infer_goal(tasks),
            }

        if "reasoning" in inc:
            decisions = self._storage.get_decisions(self._project_id)
            result["reasoning"] = {
                "decisions": [asdict(d) for d in decisions],
            }

        if "agents" in inc:
            sessions = self._storage.get_agent_sessions(self._project_id)
            result["agents"] = {
                "history": [asdict(s) for s in sessions],
            }

        return result

    def _infer_goal(self, tasks: list) -> str:
        in_progress = [t for t in tasks if t.status == "in_progress"]
        if in_progress:
            return in_progress[0].description
        pending = [t for t in tasks if t.status == "pending"]
        if pending:
            return pending[0].description
        return ""

    # ── Context Updates ──────────────────────────────────────────────

    def update_context(self, data: dict[str, Any]) -> dict[str, str]:
        """
        Accept a context update payload.  Supports keys:
        - message: {role, content}
        - file_change: {file, action, summary, diff}
        - task: {description, status}
        - decision: {question, answer, reasoning, alternatives}
        """
        results: dict[str, str] = {}

        if "message" in data:
            m = data["message"]
            mid = self._conversation.log(
                role=m.get("role", "user"),
                content=m.get("content", ""),
                agent=self._agent_name,
                context_note=m.get("context_note", ""),
            )
            results["message_id"] = mid

        if "file_change" in data:
            fc = data["file_change"]
            fid = self._storage.add_file_change(
                self._project_id,
                file_path=fc.get("file", ""),
                action=fc.get("action", "modified"),
                agent=self._agent_name,
                summary=fc.get("summary", ""),
                diff=fc.get("diff", ""),
            )
            results["file_change_id"] = str(fid)

        if "task" in data:
            t = data["task"]
            tid = self._storage.add_task(
                self._project_id,
                description=t.get("description", ""),
                task_id=t.get("id"),
                status=t.get("status", "pending"),
            )
            results["task_id"] = tid

        if "decision" in data:
            d = data["decision"]
            did = self._storage.add_decision(
                self._project_id,
                question=d.get("question", ""),
                answer=d.get("answer", ""),
                reasoning=d.get("reasoning", ""),
                alternatives=d.get("alternatives", []),
                agent=self._agent_name,
            )
            results["decision_id"] = str(did)

        return results

    # ── Convenience Methods ──────────────────────────────────────────

    def query_context(self, query: str) -> dict:
        """Search across all context tables."""
        return self._storage.search_context(self._project_id, query)

    def get_files_changed_since_switch(self) -> list[dict]:
        """Files changed since the current agent session started."""
        since = self._storage.get_last_agent_switch_time(self._project_id)
        changes = self._storage.get_file_changes(self._project_id, since=since)
        return [asdict(c) for c in changes]

    def get_conversation(self, limit: int = 50) -> list[dict]:
        msgs = self._conversation.get_recent(limit=limit)
        return [asdict(m) for m in msgs]

    def get_reasoning(self) -> list[dict]:
        decisions = self._storage.get_decisions(self._project_id)
        return [asdict(d) for d in decisions]

    def add_decision(
        self, question: str, answer: str, reasoning: str = "", alternatives: list[str] | None = None
    ) -> int:
        return self._storage.add_decision(
            self._project_id, question, answer, reasoning, alternatives or [], self._agent_name
        )

    def mark_task_complete(self, task_id: str) -> None:
        self._storage.update_task(task_id, "completed")

    def set_global_preference(self, category: str, preference: str) -> None:
        self._storage.set_global_preference(category, preference, self._agent_name)

    def add_blocker(self, description: str) -> str:
        return self._storage.add_task(
            self._project_id, description=description, status="blocked"
        )

    def get_tasks(self) -> list[dict]:
        tasks = self._storage.get_tasks(self._project_id)
        return [asdict(t) for t in tasks]

    def get_agent_history(self) -> list[dict]:
        sessions = self._storage.get_agent_sessions(self._project_id)
        return [asdict(s) for s in sessions]

    @property
    def project_id(self) -> int:
        return self._project_id

    @property
    def project_info(self) -> dict:
        return self._project_info
