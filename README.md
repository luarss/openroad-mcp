# OpenROAD MCP Server

A Model Context Protocol (MCP) server that provides access to OpenROAD commands and functionality.

## Features

- Execute OpenROAD commands through MCP
- Configurable timeout handling
- Integration with FastMCP framework

## Development

### Setup
```bash
# Install environment
uv venv
make sync
```

### Testing
```bash
# Run core tests (recommended - excludes PTY tests that may fail in some environments)
make test

# Run interactive PTY tests separately (may have file descriptor issues in CI)
make test-interactive

# Run all tests including potentially problematic PTY tests
make test-all

# Format and check code
make format
make check
```

**Note**: Interactive PTY tests are separated because they may experience file descriptor issues in certain environments (containers, CI systems). The core functionality tests (`make test`) provide comprehensive coverage of the MCP integration without these environment-specific issues.

### MCP Inspector
```bash
# Launch MCP inspector for debugging
# For STDIO transport: Set Command as "uv", Arguments as "run openroad-mcp"
make inspect
```

## Usage

The server provides the following MCP tools for interactive OpenROAD sessions:

- `interactive_openroad`: Execute commands in an interactive OpenROAD session with PTY support
- `list_interactive_sessions`: List all active interactive OpenROAD sessions
- `create_interactive_session`: Create a new interactive OpenROAD session
- `terminate_interactive_session`: Terminate an interactive OpenROAD session
- `inspect_interactive_session`: Get detailed inspection data for an interactive session
- `get_session_history`: Get command history for an interactive session
- `get_session_metrics`: Get comprehensive metrics for all interactive sessions

## Contributing

TBD

## License

TBD

---

*Built with ❤️ by Precision Innovations*
