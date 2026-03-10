# MCP CLI Testing Guide

This guide explains how to test the OpenROAD MCP server integration with Claude CLI.

## Prerequisites

1. **Claude CLI** - Install from [Anthropic documentation](https://docs.anthropic.com/en/docs/claude-cli)
   ```bash
   # Verify installation
   claude --version
   ```

2. **Anthropic API Access** - Ensure `ANTHROPIC_API_KEY` is set
   ```bash
   export ANTHROPIC_API_KEY=your-api-key
   ```

3. **OpenROAD** (for session tests) - Required only for `--all` tests
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

| Test | Description |
|------|-------------|
| `list_tools` | Verifies all 7 MCP tools are discoverable |
| `get_metrics` | Checks `get_session_metrics` returns valid response |
| `list_sessions` | Checks `list_interactive_sessions` works |

### Session Tests

These tests verify interactive session functionality (requires OpenROAD):

| Test | Description |
|------|-------------|
| `create_session` | Creates a new interactive session |
| `execute_simple_command` | Runs `puts hello` in the session |
| `execute_math_command` | Runs `expr 2 + 2` in the session |
| `get_history` | Retrieves command history |
| `inspect_session` | Inspects session state |
| `terminate_session` | Terminates the session |

### Error Handling Tests

Tests for error conditions and edge cases:

| Test | Description |
|------|-------------|
| `invalid_session_operation` | Accessing non-existent session |
| `terminate_nonexistent_session` | Terminating non-existent session |

## Running Tests

### Shell Script

```bash
# Basic usage
./scripts/test-mcp-integration.sh

# With custom claude binary
CLAUDE_BIN=/path/to/claude ./scripts/test-mcp-integration.sh

# Run all tests
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

# Custom options
python tests/mcp-integration/run_tests.py \
  --mcp-config /path/to/.mcp.json \
  --claude-bin /path/to/claude
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
├── list_tools.txt      # Output from list_tools test
├── get_metrics.txt     # Output from get_metrics test
├── report.json         # JSON report with all results
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

## Interpreting Results

### Success Indicators

- ✅ All discovery tests pass → MCP server is properly configured
- ✅ All session tests pass → OpenROAD integration is working
- ✅ All error handling tests pass → Proper error handling

### Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| "Claude CLI not found" | claude not in PATH | Install Claude CLI or set `CLAUDE_BIN` |
| "MCP config not found" | Wrong working directory | Run from project root |
| "OPENROAD_EXE not set" | OpenROAD not configured | Set `OPENROAD_EXE` environment variable |
| "expected pattern not found" | Tool output format changed | Check `.test-results/mcp-cli/*.txt` for actual output |

## Interactive Testing

For manual/interactive testing:

```bash
# Start an interactive session with MCP tools
claude --mcp-config .mcp.json

# Or with a specific prompt
claude --mcp-config .mcp.json "List all MCP tools from openroad-mcp"

# Print mode (non-interactive)
claude --mcp-config .mcp.json --print "Create an OpenROAD session"
```

## CI/CD Integration

### GitHub Actions

```yaml
- name: Test MCP Integration
  env:
    ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
  run: |
    ./scripts/test-mcp-integration.sh
```

### Docker

```bash
# Build test image
make docker-test-build

# Run tests in Docker
docker run --rm \
  -e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY \
  openroad-mcp-test \
  ./scripts/test-mcp-integration.sh --all
```

## Adding New Tests

1. Edit `tests/mcp-integration/test_cases.json`
2. Add a new test entry:

```json
{
  "name": "my_new_test",
  "description": "What this test verifies",
  "prompt": "The prompt to send to Claude",
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
