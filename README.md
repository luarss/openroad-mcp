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

## Configuration

See [mcp.md](mcp.md) for MCP client configuration and available tools.

## Contributing

We welcome contributions to OpenROAD MCP! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for detailed instructions on how to get started, our development workflow, and code standards.

## Support

If you encounter any issues or have questions, please open an issue on our [GitHub issue tracker](https://github.com/luarss/openroad-mcp/issues).

## License

TBD

---

*Built with ❤️ by Precision Innovations*
