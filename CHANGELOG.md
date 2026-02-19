# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-02-19

### Added
- Interactive PTY-based OpenROAD sessions with true terminal emulation
- Multi-session management with async support
- `interactive_openroad` tool for executing commands in persistent sessions
- `list_interactive_sessions`, `create_interactive_session`, `terminate_interactive_session`, `inspect_interactive_session`, `get_session_history`, `get_session_metrics` session lifecycle tools
- Report image tool for retrieving ORFS stage output images (#23)
- CLI entry point (`openroad-mcp`) with `--help` and version flags
- Gemini CLI integration and documentation
- Claude Code devcontainer support (#34)
- GCD timing optimization example flow targeting WNS (#35)
- Path traversal and security protection for file access
- ANSI/Unicode output decoding for clean command results
- Codecov test analytics integration
- QUICKSTART guide, ARCHITECTURE, and CONTRIBUTING documentation
- ROADMAP for planned features

[0.1.0]: https://github.com/luarss/openroad-mcp/releases/tag/v0.1.0
