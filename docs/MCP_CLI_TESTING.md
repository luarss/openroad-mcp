# MCP CLI Testing Guide

This guide explains how to test the OpenROAD MCP server integration using MCP Inspector CLI.

## Why MCP Inspector CLI?

The MCP Inspector CLI provides several advantages over Claude CLI for automated testing:

- **No authentication required** - No API key or OAuth needed
- **Direct MCP protocol access** - Deterministic JSON output
- **Faster execution** - No LLM inference delays
- **Free** - No API costs for running tests

## Prerequisites

1. **Node.js** (v18+) - Required for MCP Inspector
   ```bash
   # Verify installation
   node --version
   ```

2. **OpenROAD** (for session tests) - Required only for `--all` tests
   ```bash
   export OPENROAD_EXE=/path/to/openroad
   ```

## Quick Start

```bash
# Run discovery tests only (no OpenROAD required)
./scripts/test-mcp-integration.sh

# Run all tests including session tests (requires OpenROAD)
./scripts/test-mcp-integration.sh --all

# Using make
make test-mcp-cli
make test-mcp-cli-all
```

## Test Categories

### Discovery Tests

These tests verify MCP server discovery without requiring OpenROAD:

| Test | Method | Tool | Description |
|------|--------|------|-------------|
| `list_tools` | `tools/list` | - | Verifies all MCP tools are discoverable |
| `get_metrics` | `tools/call` | `get_session_metrics` | Checks metrics endpoint |
| `list_sessions` | `tools/call` | `list_interactive_sessions` | Lists current sessions |

### Session Tests

These tests verify interactive session functionality (requires OpenROAD):

| Test | Tool | Description |
|------|------|-------------|
| `create_session` | `create_interactive_session` | Creates a new interactive session |
| `execute_simple_command` | `interactive_openroad` | Runs `puts hello` in the session |
| `execute_math_command` | `interactive_openroad` | Runs `expr 2 + 2` in the session |
| `get_history` | `get_session_history` | Retrieves command history |
| `inspect_session` | `inspect_interactive_session` | Inspects session state |
| `terminate_session` | `terminate_interactive_session` | Terminates the session |

### Error Handling Tests

Tests for error conditions and edge cases:

| Test | Tool | Description |
|------|------|-------------|
| `invalid_session_operation` | `inspect_interactive_session` | Accessing non-existent session |
| `terminate_nonexistent_session` | `terminate_interactive_session` | Terminating non-existent session |

## Running Tests

### Shell Script

```bash
# Basic usage (discovery tests only)
./scripts/test-mcp-integration.sh

# Run all tests (requires OpenROAD)
./scripts/test-mcp-integration.sh --all

# Show help
./scripts/test-mcp-integration.sh --help
```

### Python Test Runner

```bash
# Run discovery tests only
python tests/mcp-integration/run_tests.py

# Run all tests
python tests/mcp-integration/run_tests.py --all

# Run specific category
python tests/mcp-integration/run_tests.py --category discovery

# List available tests
python tests/mcp-integration/run_tests.py --list
```

### Makefile Targets

```bash
# Run CLI tests (discovery only)
make test-mcp-cli

# Run all CLI tests in Docker (includes session tests)
make test-mcp-cli-docker
```

## Test Results

Test results are saved to `.test-results/mcp-cli/`:

```
.test-results/mcp-cli/
├── list_tools.json      # Output from list_tools test
├── get_metrics.json     # Output from get_metrics test
├── report.json          # JSON report with all results
└── ...
```

### JSON Report Format

```json
{
  "timestamp": "2025-01-15T10:30:00",
  "total_tests": 10,
  "passed": 9,
  "failed": 1,
  "results": [
    {
      "name": "list_tools",
      "category": "discovery",
      "passed": true,
      "duration_seconds": 5.2,
      "error": null,
      "expected_missing": []
    }
  ]
}
```

## Direct MCP Inspector Usage

You can also use MCP Inspector CLI directly for debugging:

```bash
# List all tools
npx @modelcontextprotocol/inspector@latest --cli \
  --config .mcp.json \
  --server openroad-mcp \
  --method tools/list

# Call a specific tool
npx @modelcontextprotocol/inspector@latest --cli \
  --config .mcp.json \
  --server openroad-mcp \
  --method tools/call \
  --tool-name get_session_metrics

# Call a tool with arguments
npx @modelcontextprotocol/inspector@latest --cli \
  --config .mcp.json \
  --server openroad-mcp \
  --method tools/call \
  --tool-name interactive_openroad \
  --tool-arg session_id=my-session \
  --tool-arg command="puts hello"
```

## CI/CD Integration

### GitHub Actions

The workflow is simplified since no authentication is required:

```yaml
- name: Run MCP Inspector tests
  run: |
    make sync
    ./scripts/test-mcp-integration.sh
```

### Docker

```bash
# Build test image
make docker-test-build

# Run tests in Docker
docker run --rm openroad-mcp-test ./scripts/test-mcp-integration.sh --all
```

## Adding New Tests

1. Edit `tests/mcp-integration/test_cases.json`
2. Add a new test entry:

```json
{
  "name": "my_new_test",
  "description": "What this test verifies",
  "method": "tools/call",
  "tool_name": "some_tool",
  "tool_args": {"arg1": "value1"},
  "expect_contains": ["expected", "output", "patterns"],
  "timeout_seconds": 60
}
```

3. Run tests to verify:
   ```bash
   python tests/mcp-integration/run_tests.py --category discovery
   ```

## Troubleshooting

### Enable Debug Output

```bash
# Save verbose output
./scripts/test-mcp-integration.sh 2>&1 | tee test-output.log
```

### Check MCP Server Logs

```bash
# Run MCP inspector for debugging
make inspect
```

### Verify MCP Configuration

```bash
# Check .mcp.json is valid JSON
cat .mcp.json | python -m json.tool
```

### Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| "Node.js not found" | node not in PATH | Install Node.js v18+ |
| "MCP config not found" | Wrong working directory | Run from project root |
| "OPENROAD_EXE not set" | OpenROAD not configured | Set `OPENROAD_EXE` environment variable |
| "expected pattern not found" | Tool output format changed | Check `.test-results/mcp-cli/*.json` for actual output |
