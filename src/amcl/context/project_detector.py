"""
ProjectDetector — identifies the current project by git root,
working directory, and config files.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

try:
    from git import InvalidGitRepositoryError, Repo
except ImportError:
    Repo = None  # type: ignore[assignment, misc]
    InvalidGitRepositoryError = Exception  # type: ignore[assignment, misc]

logger = logging.getLogger("amcl.project_detector")


def detect_project(cwd: str | None = None) -> dict:
    """
    Detect the current project.

    Args:
        cwd: Explicit project directory. If None, falls back to os.getcwd()
             and process-tree heuristics.

    Returns dict: { name, path, language, framework, git_branch, git_commit }
    """
    project_path = cwd

    if not project_path:
        current_cwd = os.getcwd()
        if current_cwd and current_cwd not in ("/", os.path.expanduser("~")):
            project_path = current_cwd
        else:
            # Server was likely launched from / or ~ by an agent.
            # This is the expected case — the caller (ensure_project)
            # should have already resolved the real path via list_roots.
            # Use cwd as a last resort.
            project_path = current_cwd

    # Ensure we have a valid path even if everything is empty
    if not project_path:
        project_path = os.getcwd() or "/"

    info: dict = {
        "name": Path(project_path).name or "unknown",
        "path": str(Path(project_path).resolve()),
        "language": "",
        "framework": "",
        "git_branch": "",
        "git_commit": "",
    }

    # ── Git detection ────────────────────────────────────────────
    if Repo is not None:
        try:
            repo = Repo(project_path, search_parent_directories=True)
            info["path"] = repo.working_dir  # git root
            info["name"] = Path(repo.working_dir).name
            if not repo.head.is_detached:
                info["git_branch"] = str(repo.active_branch)
            info["git_commit"] = repo.head.commit.hexsha[:7]
        except (InvalidGitRepositoryError, ValueError):
            pass
        except Exception as e:
            logger.debug("Git detection failed: %s", e)

    # ── Language / framework heuristics ──────────────────────────
    root = Path(info["path"])

    if (root / "package.json").exists():
        info["language"] = "javascript"
        _detect_js_framework(root, info)
    elif (root / "pyproject.toml").exists() or (root / "setup.py").exists():
        info["language"] = "python"
        _detect_py_framework(root, info)
    elif (root / "Cargo.toml").exists():
        info["language"] = "rust"
    elif (root / "go.mod").exists():
        info["language"] = "go"
    elif (root / "pom.xml").exists() or (root / "build.gradle").exists():
        info["language"] = "java"
    elif (root / "*.swift").exists() or (root / "Package.swift").exists():
        info["language"] = "swift"

    return info


def _detect_js_framework(root: Path, info: dict) -> None:
    """Detect JavaScript/TypeScript frameworks."""
    try:
        import json

        pkg = json.loads((root / "package.json").read_text())
        deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}

        if "next" in deps:
            info["framework"] = "next.js"
        elif "react" in deps:
            info["framework"] = "react"
        elif "vue" in deps:
            info["framework"] = "vue"
        elif "express" in deps:
            info["framework"] = "express"

        # Detect TypeScript
        if "typescript" in deps or (root / "tsconfig.json").exists():
            info["language"] = "typescript"
    except (json.JSONDecodeError, FileNotFoundError):
        pass


def _detect_py_framework(root: Path, info: dict) -> None:
    """Detect Python frameworks."""
    try:
        toml_text = (root / "pyproject.toml").read_text()
        if "django" in toml_text.lower():
            info["framework"] = "django"
        elif "flask" in toml_text.lower():
            info["framework"] = "flask"
        elif "fastapi" in toml_text.lower():
            info["framework"] = "fastapi"
    except FileNotFoundError:
        pass
