# MCP Configuration

## Support Matrix

| MCP Client | Supported | Transport Mode(s) | Notes |
|------------|--------|------------------|-------|
| Claude Code | ✅ | STDIO | Full support for all features |
| Claude Desktop | ⚠️ | STDIO only | Local execution only - must run on same machine as Claude Desktop |
| Gemini CLI | ✅ | STDIO | Full support for all features |
| Other MCP clients | ❌ | - | Unsupported, open for contributions |

## Configuration for Claude Code

To use OpenROAD MCP with Claude Code, add the following configuration to your Claude Code MCP settings:

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

Replace `/path/to/openroad-mcp` with the actual path to your openroad-mcp installation directory.

## Configuration for Claude Desktop (Local Only)

**Important**: Claude Desktop only supports STDIO transport and must run the MCP server locally on the same machine. Only HTTPS Remote servers are supported by Claude Desktop.

### Requirements
- OpenROAD must be installed on the same machine as Claude Desktop
- The MCP server runs as a local process via STDIO

### Configuration

Add the following to your Claude Desktop MCP settings (`claude_desktop_config.json`):

**macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
**Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

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

Replace `/path/to/openroad-mcp` with the actual path to your openroad-mcp installation directory.

### Using Docker (Optional)

You can run the MCP server in a Docker container on your local machine:

**Build the Docker image:**
```bash
docker build -t openroad-mcp:latest /path/to/openroad-mcp
```

**Configure Claude Desktop to use Docker:**
```json
{
  "mcpServers": {
    "openroad-mcp": {
      "command": "docker",
      "args": [
        "run",
        "-i",
        "--rm",
        "openroad-mcp:latest"
      ]
    }
  }
}
```

This runs the MCP server in an isolated Docker container while maintaining STDIO communication with Claude Desktop.

## Verification

After configuration, restart Claude Code and verify the MCP server is running:

1. The server should automatically start when Claude Code launches
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

## Troubleshooting

If the MCP server fails to start:

1. Ensure `uv` is installed and available in your PATH
2. Verify the path to openroad-mcp is correct
3. Check that all dependencies are installed: `make sync`
4. Review Claude Code logs for specific error messages
