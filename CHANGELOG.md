# Changelog

All notable changes to this project will be documented in this file.

The format is loosely based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.3.2]

- **Claude Code:** `amcl setup` now registers the MCP server in
  `~/.claude.json` (user + local scope), project `.mcp.json`, and adds
  `mcp__amcl` to Claude Code permissions. Previously only Claude Desktop
  and `CLAUDE.md` rules were configured, so tools never connected.
- Open-source release prep: `LICENSE`, `CONTRIBUTING.md`, `SECURITY.md`,
  `CODE_OF_CONDUCT.md`, GitHub CI, issue/PR templates; cleaned tracked
  build artifacts from version control.
- Fixed `amcl-share-backend` gitignore so `.env.local.example` can be
  committed; expanded root `.gitignore` for Node/Next build outputs.

## [1.3.1]

- Bumped SQLite connection timeout, refined sharing serialization, and
  fixed a number of timestamp / project-detection edge cases.

## [1.3.0]

- Added Codex to the agent auto-detection list.
- Enhanced the sharing flow with token tracking and conversation
  summaries.

See `git log` for the full history prior to this changelog.
