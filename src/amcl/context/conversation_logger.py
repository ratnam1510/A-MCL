"""
ConversationLogger — records agent ↔ user messages
with attribution, timestamps, and simple summarization.
"""

from __future__ import annotations

from amcl.storage.storage_manager import StorageManager
from amcl.types import ConversationMessage


class ConversationLogger:
    """Thin wrapper for message persistence + summarization."""

    def __init__(self, storage: StorageManager, project_id: int) -> None:
        self._storage = storage
        self._project_id = project_id

    def log(
        self,
        role: str,
        content: str,
        agent: str = "",
        context_note: str = "",
    ) -> str:
        """Record a message and return its id."""
        return self._storage.add_message(
            project_id=self._project_id,
            role=role,
            content=content,
            agent=agent,
            context_note=context_note,
        )

    def get_recent(self, limit: int = 50) -> list[ConversationMessage]:
        """Return the most recent messages (oldest → newest)."""
        return self._storage.get_messages(self._project_id, limit=limit)

    def summarize(self, max_messages: int = 200) -> str:
        """
        Generate a plain-text summary of the conversation.

        Uses extractive summarization: takes the first user message
        (the original goal) plus the most recent messages for context.
        """
        messages = self._storage.get_messages(self._project_id, limit=max_messages)
        if not messages:
            return "No conversation history."

        lines: list[str] = []

        # Opening goal
        first_user = next((m for m in messages if m.role == "user"), None)
        if first_user:
            lines.append(f"Original goal: {first_user.content[:300]}")

        # Agent attributions
        agents_seen = list(dict.fromkeys(m.agent for m in messages if m.agent))
        if agents_seen:
            lines.append(f"Agents involved: {', '.join(agents_seen)}")

        # Last few exchanges
        tail = messages[-6:]
        lines.append(f"\nRecent activity ({len(tail)} messages):")
        for m in tail:
            agent_tag = f" [{m.agent}]" if m.agent else ""
            snippet = m.content[:200].replace("\n", " ")
            lines.append(f"  {m.role}{agent_tag}: {snippet}")

        lines.append(f"\nTotal messages: {len(messages)}")
        return "\n".join(lines)
