"""
A/MCL shared type definitions.

All dataclasses match the PRD context schema, used across
storage, context, and MCP layers.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


def _now() -> str:
    """UTC timestamp in SQLite-compatible format."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


# ── Project ──────────────────────────────────────────────────────────

@dataclass
class GitInfo:
    branch: str = ""
    commit: str = ""


@dataclass
class ProjectMeta:
    name: str = ""
    path: str = ""
    language: str = ""
    framework: str = ""
    git: GitInfo = field(default_factory=GitInfo)


# ── Conversation ─────────────────────────────────────────────────────

@dataclass
class ConversationMessage:
    id: str = ""
    timestamp: str = field(default_factory=_now)
    role: str = "user"  # "user" | "assistant" | "system"
    content: str = ""
    agent: str = ""
    context_note: str = ""


# ── Files ────────────────────────────────────────────────────────────

@dataclass
class FileChange:
    file: str = ""
    action: str = "modified"  # "created" | "modified" | "deleted"
    timestamp: str = field(default_factory=_now)
    agent: str = ""
    summary: str = ""
    diff: str = ""


# ── Tasks ────────────────────────────────────────────────────────────

@dataclass
class TaskItem:
    id: str = ""
    description: str = ""
    status: str = "pending"  # "pending" | "in_progress" | "completed" | "blocked"
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)


# ── Decisions ────────────────────────────────────────────────────────

@dataclass
class Decision:
    timestamp: str = field(default_factory=_now)
    question: str = ""
    answer: str = ""
    reasoning: str = ""
    alternatives: list[str] = field(default_factory=list)
    agent: str = ""


# ── Agent Sessions ───────────────────────────────────────────────────

@dataclass
class AgentSession:
    agent: str = ""
    started: str = field(default_factory=_now)
    ended: Optional[str] = None
    reason_for_switch: Optional[str] = None


# ── Full Context Snapshot ────────────────────────────────────────────

@dataclass
class ContextSnapshot:
    """Complete project context returned to agents."""
    project: ProjectMeta = field(default_factory=ProjectMeta)
    conversation: dict[str, Any] = field(default_factory=dict)
    files: dict[str, Any] = field(default_factory=dict)
    state: dict[str, Any] = field(default_factory=dict)
    reasoning: dict[str, Any] = field(default_factory=dict)
    agents: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, default=str)
