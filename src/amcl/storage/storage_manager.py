"""
StorageManager — typed CRUD layer over the A/MCL SQLite database.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path
from typing import Optional

from amcl.storage.database import get_connection
from amcl.types import (
    AgentSession,
    ConversationMessage,
    Decision,
    FileChange,
    TaskItem,
    _now,
)


class StorageManager:
    """High-level CRUD interface wrapping the SQLite database."""

    def __init__(self, db_path: Path | None = None) -> None:
        self._conn = get_connection(db_path)

    def close(self) -> None:
        self._conn.close()

    # ── Projects ─────────────────────────────────────────────────────

    def get_or_create_project(
        self,
        path: str,
        name: str = "",
        language: str = "",
        framework: str = "",
        git_branch: str = "",
        git_commit: str = "",
    ) -> int:
        """Return the project id, creating the row if needed."""
        row = self._conn.execute(
            "SELECT id FROM projects WHERE path = ?", (path,)
        ).fetchone()
        if row:
            # Update metadata on reconnect
            self._conn.execute(
                """UPDATE projects
                   SET name=?, language=?, framework=?,
                       git_branch=?, git_commit=?, updated_at=datetime('now')
                   WHERE id=?""",
                (name or "", language, framework, git_branch, git_commit, row["id"]),
            )
            self._conn.commit()
            return row["id"]

        cur = self._conn.execute(
            """INSERT INTO projects (name, path, language, framework, git_branch, git_commit)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (name or Path(path).name, path, language, framework, git_branch, git_commit),
        )
        self._conn.commit()
        return cur.lastrowid  # type: ignore[return-value]

    def get_project_info(self, project_id: int) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM projects WHERE id = ?", (project_id,)
        ).fetchone()
        return dict(row) if row else None

    # ── Messages ─────────────────────────────────────────────────────

    def add_message(
        self,
        project_id: int,
        role: str,
        content: str,
        agent: str = "",
        context_note: str = "",
        msg_id: str | None = None,
    ) -> str:
        mid = msg_id or f"msg-{uuid.uuid4().hex[:8]}"
        self._conn.execute(
            """INSERT INTO messages (id, project_id, role, content, agent, context_note)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (mid, project_id, role, content, agent, context_note),
        )
        self._conn.commit()
        return mid

    def get_messages(
        self, project_id: int, limit: int = 50, since: str | None = None
    ) -> list[ConversationMessage]:
        if since:
            rows = self._conn.execute(
                """SELECT * FROM messages
                   WHERE project_id = ? AND timestamp >= ?
                   ORDER BY timestamp DESC
                   LIMIT ?""",
                (project_id, since, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                """SELECT * FROM messages
                   WHERE project_id = ?
                   ORDER BY timestamp DESC
                   LIMIT ?""",
                (project_id, limit),
            ).fetchall()
        return [
            ConversationMessage(
                id=r["id"],
                timestamp=r["timestamp"],
                role=r["role"],
                content=r["content"],
                agent=r["agent"],
                context_note=r["context_note"],
            )
            for r in reversed(rows)  # oldest first
        ]

    # ── File Changes ─────────────────────────────────────────────────

    def add_file_change(
        self,
        project_id: int,
        file_path: str,
        action: str = "modified",
        agent: str = "",
        summary: str = "",
        diff: str = "",
    ) -> int:
        cur = self._conn.execute(
            """INSERT INTO file_changes (project_id, file_path, action, agent, summary, diff)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (project_id, file_path, action, agent, summary, diff),
        )
        self._conn.commit()
        return cur.lastrowid  # type: ignore[return-value]

    def get_file_changes(
        self, project_id: int, since: str | None = None
    ) -> list[FileChange]:
        if since:
            rows = self._conn.execute(
                """SELECT * FROM file_changes
                   WHERE project_id = ? AND timestamp >= ?
                   ORDER BY timestamp""",
                (project_id, since),
            ).fetchall()
        else:
            rows = self._conn.execute(
                """SELECT * FROM file_changes
                   WHERE project_id = ?
                   ORDER BY timestamp""",
                (project_id,),
            ).fetchall()
        return [
            FileChange(
                file=r["file_path"],
                action=r["action"],
                timestamp=r["timestamp"],
                agent=r["agent"],
                summary=r["summary"],
                diff=r["diff"],
            )
            for r in rows
        ]

    # ── Tasks ────────────────────────────────────────────────────────

    def add_task(
        self,
        project_id: int,
        description: str,
        task_id: str | None = None,
        status: str = "pending",
    ) -> str:
        tid = task_id or f"t-{uuid.uuid4().hex[:6]}"
        self._conn.execute(
            """INSERT INTO tasks (id, project_id, description, status)
               VALUES (?, ?, ?, ?)""",
            (tid, project_id, description, status),
        )
        self._conn.commit()
        return tid

    def update_task(self, task_id: str, status: str) -> None:
        self._conn.execute(
            """UPDATE tasks SET status = ?, updated_at = datetime('now')
               WHERE id = ?""",
            (status, task_id),
        )
        self._conn.commit()

    def get_tasks(self, project_id: int, since: str | None = None) -> list[TaskItem]:
        if since:
            rows = self._conn.execute(
                "SELECT * FROM tasks WHERE project_id = ? AND created_at >= ? ORDER BY created_at",
                (project_id, since),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM tasks WHERE project_id = ? ORDER BY created_at",
                (project_id,),
            ).fetchall()
        return [
            TaskItem(
                id=r["id"],
                description=r["description"],
                status=r["status"],
                created_at=r["created_at"],
                updated_at=r["updated_at"],
            )
            for r in rows
        ]

    # ── Decisions ────────────────────────────────────────────────────

    def add_decision(
        self,
        project_id: int,
        question: str,
        answer: str,
        reasoning: str = "",
        alternatives: list[str] | None = None,
        agent: str = "",
    ) -> int:
        cur = self._conn.execute(
            """INSERT INTO decisions
               (project_id, question, answer, reasoning, alternatives, agent)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                project_id,
                question,
                answer,
                reasoning,
                json.dumps(alternatives or []),
                agent,
            ),
        )
        self._conn.commit()
        return cur.lastrowid  # type: ignore[return-value]

    def get_decisions(self, project_id: int, since: str | None = None) -> list[Decision]:
        if since:
            rows = self._conn.execute(
                "SELECT * FROM decisions WHERE project_id = ? AND timestamp >= ? ORDER BY timestamp",
                (project_id, since),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM decisions WHERE project_id = ? ORDER BY timestamp",
                (project_id,),
            ).fetchall()
        return [
            Decision(
                timestamp=r["timestamp"],
                question=r["question"],
                answer=r["answer"],
                reasoning=r["reasoning"],
                alternatives=json.loads(r["alternatives"]),
                agent=r["agent"],
            )
            for r in rows
        ]

    # ── Global Preferences ───────────────────────────────────────────

    def set_global_preference(self, category: str, preference: str, agent: str) -> None:
        self._conn.execute(
            """INSERT INTO global_preferences (category, preference, source_agent)
               VALUES (?, ?, ?)
               ON CONFLICT(category) DO UPDATE SET
                   preference=excluded.preference,
                   source_agent=excluded.source_agent,
                   updated_at=datetime('now')""",
            (category, preference, agent),
        )
        self._conn.commit()

    def get_global_preferences(self) -> dict[str, str]:
        rows = self._conn.execute(
            "SELECT category, preference FROM global_preferences ORDER BY category"
        ).fetchall()
        return {r["category"]: r["preference"] for r in rows}

    # ── Agent Sessions ───────────────────────────────────────────────

    def start_agent_session(
        self, project_id: int, agent: str
    ) -> int:
        """Close any open sessions and start a new one."""
        # Close previous open session
        self._conn.execute(
            """UPDATE agent_sessions
               SET ended = datetime('now'),
                   reason_for_switch = 'Agent switch detected'
               WHERE project_id = ? AND ended IS NULL""",
            (project_id,),
        )
        cur = self._conn.execute(
            """INSERT INTO agent_sessions (project_id, agent)
               VALUES (?, ?)""",
            (project_id, agent),
        )
        self._conn.commit()
        return cur.lastrowid  # type: ignore[return-value]

    def end_agent_session(
        self,
        project_id: int,
        reason: str = "",
    ) -> None:
        self._conn.execute(
            """UPDATE agent_sessions
               SET ended = datetime('now'), reason_for_switch = ?
               WHERE project_id = ? AND ended IS NULL""",
            (reason, project_id),
        )
        self._conn.commit()

    def get_agent_sessions(self, project_id: int, since: str | None = None) -> list[AgentSession]:
        if since:
            rows = self._conn.execute(
                """SELECT * FROM agent_sessions
                   WHERE project_id = ? AND started >= ?
                   ORDER BY started""",
                (project_id, since),
            ).fetchall()
        else:
            rows = self._conn.execute(
                """SELECT * FROM agent_sessions
                   WHERE project_id = ?
                   ORDER BY started""",
                (project_id,),
            ).fetchall()
        return [
            AgentSession(
                agent=r["agent"],
                started=r["started"],
                ended=r["ended"],
                reason_for_switch=r["reason_for_switch"],
            )
            for r in rows
        ]

    def get_last_agent_switch_time(self, project_id: int) -> str | None:
        """Return the start time of the current agent session."""
        row = self._conn.execute(
            """SELECT started FROM agent_sessions
               WHERE project_id = ? AND ended IS NULL
               ORDER BY started DESC LIMIT 1""",
            (project_id,),
        ).fetchone()
        return row["started"] if row else None

    # ── Search ───────────────────────────────────────────────────────

    def search_context(self, project_id: int, query: str, since: str | None = None) -> dict:
        """Full-text search across messages, decisions, and tasks using FTS5."""
        # Sanitize query for FTS5 syntax (wrap in quotes if not already valid)
        clean_query = query.replace('"', '""')
        fts_query = f'"{clean_query}"*'
        
        # Fallback LIKE query for tasks which aren't FTS5 indexed yet
        q = f"%{query}%"

        since_str = since if since else "1970-01-01"

        messages = self._conn.execute(
            """SELECT m.* 
               FROM messages m
               JOIN messages_fts fts ON m.rowid = fts.rowid
               WHERE m.project_id = ? AND m.timestamp >= ? AND messages_fts MATCH ?
               ORDER BY m.timestamp LIMIT 20""",
            (project_id, since_str, fts_query),
        ).fetchall()

        decisions = self._conn.execute(
            """SELECT d.* 
               FROM decisions d
               JOIN decisions_fts fts ON d.id = fts.rowid
               WHERE d.project_id = ? AND d.timestamp >= ? AND decisions_fts MATCH ?
               ORDER BY d.timestamp LIMIT 20""",
            (project_id, since_str, fts_query),
        ).fetchall()

        # Tasks still use regular LIKE since they're metadata-heavy
        tasks = self._conn.execute(
            """SELECT * FROM tasks
               WHERE project_id = ? AND created_at >= ? AND description LIKE ?
               ORDER BY created_at LIMIT 20""",
            (project_id, since_str, q),
        ).fetchall()

        # Also search file changes now that we have FTS5!
        file_changes = self._conn.execute(
            """SELECT fc.* 
               FROM file_changes fc
               JOIN file_changes_fts fts ON fc.id = fts.rowid
               WHERE fc.project_id = ? AND fc.timestamp >= ? AND file_changes_fts MATCH ?
               ORDER BY fc.timestamp LIMIT 20""",
            (project_id, since_str, fts_query),
        ).fetchall()

        return {
            "messages": [dict(r) for r in messages],
            "decisions": [dict(r) for r in decisions],
            "tasks": [dict(r) for r in tasks],
            "file_changes": [dict(r) for r in file_changes],
        }
