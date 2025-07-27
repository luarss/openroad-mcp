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
# Run all tests
make test

# Format and check code
make format
make check
```

### MCP Inspector
```bash
# Launch MCP inspector for debugging
# For STDIO transport: Set Command as "uv", Arguments as "run openroad-mcp"
make inspect
```

## Usage

The server provides the following MCP tool:

- `execute_openroad_command`: Execute OpenROAD commands with configurable timeout

## Contributing

TBD

## License

TBD

---

*Built with ❤️ by Precision Innovations*
