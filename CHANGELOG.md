# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.4.2] - 2026-03-29

### Fixed
- Docker build targeting wrong stage, causing missing OCI annotation required by MCP registry
- Docker image tag mismatch causing MCP registry publish to fail

## [0.4.0] - 2026-03-29

### Added
- MCP registry publishing to release pipeline ([#93](https://github.com/luarss/openroad-mcp/pull/93))
- Cross-platform validation and setup scripts ([#76](https://github.com/luarss/openroad-mcp/pull/76))
- Comprehensive performance benchmarks for OpenROAD tool calls ([#84](https://github.com/luarss/openroad-mcp/pull/84))

### Changed
- Consolidated Dockerfile.test into unified multi-stage Dockerfile ([#88](https://github.com/luarss/openroad-mcp/pull/88))
- Scaled concurrent session test to 50+ with p99/p95 latency metrics ([#86](https://github.com/luarss/openroad-mcp/pull/86))
- Updated ROADMAP.md
- Bumped requests dependency version

## [0.3.0] - 2026-03-25

### Added
- Production Dockerfile with multi-stage build, non-root user, and GHCR publishing workflow ([#46](https://github.com/luarss/openroad-mcp/pull/46))
- `--init` flag to docker run commands in Makefile for proper signal handling ([#80](https://github.com/luarss/openroad-mcp/pull/80))

### Fixed
- Restored 15 skipped TestSessionManager tests ([#75](https://github.com/luarss/openroad-mcp/pull/75))
- Replaced `cleanup()` with `cleanup_all()` in test_session_manager ([#73](https://github.com/luarss/openroad-mcp/pull/73))

### Changed
- Removed dead `skip_fd_issues` marker and unused imports from test_interactive_pty.py ([#82](https://github.com/luarss/openroad-mcp/pull/82))

## [0.2.0] - 2026-03-18

### Added
- `streamable-http` transport mode support in the CLI (#54)
- Whitelist and ask-permission commands for session access control (#36)
- Token efficiency benchmarks for MCP responses (#53)

### Changed
- Upgraded dependencies to address Dependabot security alerts (#70, #71)
- Updated inspector version in Makefile
- Updated Gemini MCP settings

### Refactored
- Reduced dead code and duplications across the codebase (#59)

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

[0.4.0]: https://github.com/luarss/openroad-mcp/releases/tag/v0.4.0
[0.3.0]: https://github.com/luarss/openroad-mcp/releases/tag/v0.3.0
[0.2.0]: https://github.com/luarss/openroad-mcp/releases/tag/v0.2.0
[0.1.0]: https://github.com/luarss/openroad-mcp/releases/tag/v0.1.0
