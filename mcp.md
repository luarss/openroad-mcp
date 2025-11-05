# MCP Configuration

## Support Matrix

| MCP Client | Supported | Transport Mode(s) | Notes |
|------------|--------|------------------|-------|
| Claude Code | ✅ | STDIO | Full support for all features |
| Claude Desktop | ⚠️ | STDIO only | Local execution only - must run on same machine as Claude Desktop |
| Gemini CLI | ✅ | STDIO | Full support for all features |
| Other MCP clients | ❌ | - | Unsupported, open for contributions |

## Installation

<details>
<summary><b>Claude Code</b></summary>

Add the following configuration to your Claude Code MCP settings:

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

</details>

<details>
<summary><b>Claude Desktop</b></summary>

**Important**: Claude Desktop only supports STDIO transport and must run the MCP server locally on the same machine.

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

</details>

<details>
<summary><b>Gemini CLI</b></summary>

Add the following configuration to your Gemini CLI MCP settings:

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

</details>

<details>
<summary><b>Docker</b></summary>

You can run the MCP server in a Docker container on your local machine:

**Build the Docker image:**
```bash
docker build -t openroad-mcp:latest /path/to/openroad-mcp
```

**Configure your MCP client to use Docker:**
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

This runs the MCP server in an isolated Docker container while maintaining STDIO communication with your MCP client.

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
