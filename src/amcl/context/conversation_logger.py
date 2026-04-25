"""
ConversationLogger — records agent ↔ user messages
with attribution, timestamps, and simple summarization.
"""

from __future__ import annotations

from amcl.context.message_filters import (
    normalize_message_content,
    parse_message_context_note,
)
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

    def get_recent(
        self,
        limit: int = 50,
        since: str | None = None,
        include_noise: bool = False,
    ) -> list[ConversationMessage]:
        """Return the most recent messages (oldest → newest)."""
        return self._storage.get_messages(
            self._project_id,
            limit=limit,
            since=since,
            include_noise=include_noise,
        )

    def get_compact(self, max_messages: int = 120, since: str | None = None) -> dict[str, str | int]:
        """Return a compact high-signal conversation packet."""
        messages = self.get_recent(limit=max_messages, since=since)
        if not messages:
            return {
                "original_goal": "",
                "latest_user_request": "",
                "latest_assistant_outcome": "",
                "files_mentioned": [],
                "commands_mentioned": [],
                "blockers": [],
                "symbols_mentioned": [],
                "messages_considered": 0,
            }

        first_user = next((m for m in messages if m.role == "user"), None)
        last_user = next((m for m in reversed(messages) if m.role == "user"), None)
        last_assistant = next((m for m in reversed(messages) if m.role == "assistant"), None)
        files: list[str] = []
        commands: list[str] = []
        blockers: list[str] = []
        symbols: list[str] = []
        seen_files: set[str] = set()
        seen_commands: set[str] = set()
        seen_blockers: set[str] = set()
        seen_symbols: set[str] = set()
        for msg in messages:
            signals = parse_message_context_note(msg.context_note).get("signals", {})
            if not isinstance(signals, dict):
                continue
            for file_ref in signals.get("files", []):
                if file_ref not in seen_files and len(files) < 6:
                    seen_files.add(file_ref)
                    files.append(file_ref)
            for command in signals.get("commands", []):
                if command not in seen_commands and len(commands) < 4:
                    seen_commands.add(command)
                    commands.append(command)
            for blocker in signals.get("blockers", []):
                if blocker not in seen_blockers and len(blockers) < 3:
                    seen_blockers.add(blocker)
                    blockers.append(blocker)
            for symbol in signals.get("symbols", []):
                if symbol not in seen_symbols and len(symbols) < 8:
                    seen_symbols.add(symbol)
                    symbols.append(symbol)

        return {
            "original_goal": first_user.content[:220] if first_user else "",
            "latest_user_request": last_user.content[:220] if last_user else "",
            "latest_assistant_outcome": last_assistant.content[:220] if last_assistant else "",
            "files_mentioned": files,
            "commands_mentioned": commands,
            "blockers": blockers,
            "symbols_mentioned": symbols,
            "messages_considered": len(messages),
        }

    def get_recent_packet(
        self,
        limit: int = 8,
        max_chars: int | None = 220,
        since: str | None = None,
    ) -> list[dict[str, str | bool | int | None]]:
        """Return compact message previews for token-efficient retrieval."""
        packet: list[dict[str, str | bool | int | None]] = []
        for msg in self.get_recent(limit=limit, since=since):
            meta = parse_message_context_note(msg.context_note)
            content = normalize_message_content(msg.content)
            truncated = False
            if max_chars is not None:
                truncated = len(content) > max_chars
                if truncated:
                    content = content[: max_chars - 1].rstrip() + "…"

            packet.append({
                "id": msg.id,
                "timestamp": msg.timestamp,
                "role": msg.role,
                "agent": msg.agent,
                "content": content,
                "truncated": truncated,
                "storage": str(meta.get("storage", "full")),
                "raw_chars": meta.get("raw_chars"),
                "summary_source": meta.get("summary_source"),
                "signals": meta.get("signals", {}),
                "source": meta.get("source"),
            })

        return packet

    def summarize(self, max_messages: int = 200, since: str | None = None) -> str:
        """
        Generate a plain-text summary of the conversation.

        Uses extractive summarization: takes the first user message
        (the original goal) plus the most recent messages for context.
        """
        messages = self._storage.get_messages(
            self._project_id,
            limit=max_messages,
            since=since,
            include_noise=False,
        )
        if not messages:
            return "No conversation history."

        compact = self.get_compact(max_messages=max_messages, since=since)
        lines: list[str] = []

        # Opening goal
        if compact["original_goal"]:
            lines.append(f"Original goal: {compact['original_goal']}")

        if compact["latest_user_request"]:
            lines.append(f"Latest user request: {compact['latest_user_request']}")

        if compact["latest_assistant_outcome"]:
            lines.append(f"Latest assistant outcome: {compact['latest_assistant_outcome']}")

        # Agent attributions
        agents_seen = list(dict.fromkeys(m.agent for m in messages if m.agent))
        if agents_seen:
            lines.append(f"Agents involved: {', '.join(agents_seen)}")

        # Last few exchanges
        tail = messages[-4:]
        lines.append(f"\nRecent activity ({len(tail)} messages):")
        for m in tail:
            agent_tag = f" [{m.agent}]" if m.agent else ""
            snippet = m.content[:200].replace("\n", " ")
            lines.append(f"  {m.role}{agent_tag}: {snippet}")

        lines.append(f"\nTotal messages: {len(messages)}")
        return "\n".join(lines)

    def summarize_brief(self, max_messages: int = 120, since: str | None = None) -> str:
        """Return a shorter summary for token-efficient default retrieval."""
        messages = self._storage.get_messages(
            self._project_id,
            limit=max_messages,
            since=since,
            include_noise=False,
        )
        if not messages:
            return "No conversation history."

        compact = self.get_compact(max_messages=max_messages, since=since)
        lines: list[str] = []

        if compact["original_goal"]:
            lines.append(f"Original goal: {compact['original_goal']}")
        if compact["latest_user_request"]:
            lines.append(f"Latest user request: {compact['latest_user_request']}")
        if compact["latest_assistant_outcome"]:
            lines.append(f"Latest assistant outcome: {compact['latest_assistant_outcome']}")
        if compact["files_mentioned"]:
            lines.append(f"Recent files: {', '.join(compact['files_mentioned'])}")
        if compact["commands_mentioned"]:
            lines.append(f"Recent commands: {', '.join(compact['commands_mentioned'])}")
        if compact["blockers"]:
            lines.append(f"Open blockers: {' | '.join(compact['blockers'])}")
        if compact["symbols_mentioned"]:
            lines.append(f"Recent symbols: {', '.join(compact['symbols_mentioned'])}")

        agents_seen = list(dict.fromkeys(m.agent for m in messages if m.agent))
        if agents_seen:
            lines.append(f"Agents involved: {', '.join(agents_seen)}")

        lines.append(f"Total messages: {len(messages)}")
        return "\n".join(lines)
