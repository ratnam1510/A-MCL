"""
FileWatcher — monitors a project directory for file changes
using watchdog, recording creates/modifies/deletes to storage.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from amcl.storage.storage_manager import StorageManager

logger = logging.getLogger("amcl.file_watcher")

# Directories never worth tracking
_IGNORE_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv",
    "dist", "build", ".next", ".nuxt", ".cache", ".tox",
    "egg-info", ".mypy_cache", ".ruff_cache",
}

# Extensions never worth tracking
_IGNORE_EXTS = {
    ".pyc", ".pyo", ".o", ".so", ".dylib", ".class",
    ".db", ".sqlite", ".sqlite3", ".lock",
}


class _ChangeHandler(FileSystemEventHandler):
    """Watchdog handler that writes file changes to storage."""

    def __init__(self, storage: StorageManager, project_id: int, root: str) -> None:
        self._storage = storage
        self._project_id = project_id
        self._root = root

    def _should_ignore(self, path: str) -> bool:
        parts = Path(path).parts
        if any(p in _IGNORE_DIRS for p in parts):
            return True
        if Path(path).suffix in _IGNORE_EXTS:
            return True
        return False

    def _relative(self, path: str) -> str:
        try:
            return str(Path(path).relative_to(self._root))
        except ValueError:
            return path

    def on_created(self, event: FileSystemEvent) -> None:
        if event.is_directory or self._should_ignore(event.src_path):
            return
        rel = self._relative(event.src_path)
        logger.debug("File created: %s", rel)
        self._storage.add_file_change(
            self._project_id, rel, action="created"
        )

    def on_modified(self, event: FileSystemEvent) -> None:
        if event.is_directory or self._should_ignore(event.src_path):
            return
        rel = self._relative(event.src_path)
        logger.debug("File modified: %s", rel)
        self._storage.add_file_change(
            self._project_id, rel, action="modified"
        )

    def on_deleted(self, event: FileSystemEvent) -> None:
        if event.is_directory or self._should_ignore(event.src_path):
            return
        rel = self._relative(event.src_path)
        logger.debug("File deleted: %s", rel)
        self._storage.add_file_change(
            self._project_id, rel, action="deleted"
        )


class FileWatcher:
    """
    Watches a project directory for file changes and persists them.
    Start / stop are safe to call multiple times.
    """

    def __init__(
        self,
        storage: StorageManager,
        project_id: int,
        project_root: str,
    ) -> None:
        self._storage = storage
        self._project_id = project_id
        self._root = project_root
        self._observer: Optional[Observer] = None

    def start(self) -> None:
        if self._observer is not None:
            return
        handler = _ChangeHandler(self._storage, self._project_id, self._root)
        self._observer = Observer()
        self._observer.schedule(handler, self._root, recursive=True)
        self._observer.daemon = True
        self._observer.start()
        logger.info("File watcher started for %s", self._root)

    def stop(self) -> None:
        if self._observer is not None:
            self._observer.stop()
            self._observer.join(timeout=2)
            self._observer = None
            logger.info("File watcher stopped")
