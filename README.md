# OpenROAD MCP Server

A Model Context Protocol (MCP) server that provides tools for interacting with OpenROAD and ORFS (OpenROAD Flow Scripts).

## Features

- **Interactive OpenROAD sessions** - Execute commands in persistent OpenROAD sessions with PTY support
- **Session management** - Create, list, inspect, and terminate multiple sessions
- **Command history** - Access full command history for any session
- **Performance metrics** - Get comprehensive metrics across all sessions
- **Report visualization** - List and read report images from ORFS runs

## Requirements

- OpenROAD installed and available in your PATH
- Python 3.13 or higher
- `uv` package manager (for running the server)

## Support Matrix

| MCP Client | Supported | Transport Mode(s) | Notes |
|------------|--------|------------------|-------|
| Claude Code | ✅ | STDIO | Full support for all features |
| Claude Desktop | ✅ | STDIO | Local execution - runs on same machine |
| Gemini CLI | ✅ | STDIO | Full support for all features |
| Other MCP clients | ⚠️ | STDIO | Should work with standard STDIO transport |

## Getting Started

### Standard Configuration

The basic configuration for all MCP clients:

```json
{
  "mcpServers": {
    "openroad-mcp": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/luarss/openroad-mcp",
        "openroad-mcp"
      ]
    }
  }
}
```

For local development, use:

```json
{
  "mcpServers": {
    "openroad-mcp": {
      "command": "uv",
      "args": [
        "--directory",
        "/path/to/openroad-mcp",
        "run",
        "openroad-mcp"
      ]
    }
  }
}
```

## Installation

<details>
<summary><b>Claude Code</b></summary>

Use the Claude Code CLI to add the OpenROAD MCP server:

```bash
claude mcp add --transport stdio openroad-mcp -- uvx --from git+https://github.com/luarss/openroad-mcp openroad-mcp
```

</details>

<details>
<summary><b>Claude Desktop</b></summary>

Follow the MCP install [guide](https://modelcontextprotocol.io/quickstart/user), using the [standard configuration](#standard-configuration) above.

</details>

<details>
<summary><b>Gemini CLI</b></summary>

Follow the [Gemini MCP install guide](https://ai.google.dev/gemini-api/docs/model-context-protocol), using the [standard configuration](#standard-configuration) above.

</details>

<details>
<summary><b>Docker</b></summary>

🚧 **Work in Progress**: Docker deployment via GitHub Container Registry (GHCR) is coming soon.

</details>

## Verification

After configuration, restart your MCP client and verify the MCP server is running:

1. The server should automatically start when your MCP client launches
2. You can use OpenROAD tools through the MCP interface
3. Check logs for any startup errors if tools are not available

## Available Tools

Once configured, the following tools are available:

- `interactive_openroad` - Execute commands in an interactive OpenROAD session
- `create_interactive_session` - Create a new OpenROAD session
- `list_interactive_sessions` - List all active sessions
- `terminate_interactive_session` - Terminate a session
- `inspect_interactive_session` - Get detailed session information
- `get_session_history` - View command history
- `get_session_metrics` - Get performance metrics
- `list_report_images` - List ORFS report directory images
- `read_report_image` - Read a ORFS report image

## Troubleshooting

If the MCP server fails to start:

1. Ensure `uv` is installed and available in your PATH
2. Verify the path to openroad-mcp is correct
3. Check that all dependencies are installed: `make sync`
4. Review your MCP client logs for specific error messages

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

## Contributing

We welcome contributions to OpenROAD MCP! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for detailed instructions on how to get started, our development workflow, and code standards.

## Support

If you encounter any issues or have questions, please open an issue on our [GitHub issue tracker](https://github.com/luarss/openroad-mcp/issues).

## License

BSD 3-Clause License. See [LICENSE](LICENSE) file.

---

*Built with ❤️ by Precision Innovations*
