MCP_SERVER_REQUEST_TIMEOUT:= 99999999999
MCP_REQUEST_MAX_TOTAL_TIMEOUT:= 99999999999

.PHONY: sync
sync:
	@uv sync --all-extras --inexact

.PHONY: reqs
reqs:
	@rm -f requirements.txt
	@rm -f requirements-test.txt
	@uv sync --all-extras --inexact  --upgrade
	@uv pip compile --output-file=requirements.txt pyproject.toml --upgrade
	@uv pip compile --output-file=requirements-test.txt pyproject.toml --extra dev  --upgrade

.PHONY: format
format:
	@uv run ruff format .
	@uv run ruff check . --fix

.PHONY: check
check:
	@uv run ruff check
	@uv run mypy .
	@uv run pre-commit run --all-files

# Test targets
.PHONY: test
test:
	@echo "Running core tests (excluding interactive PTY tests)..."
	@uv run pytest --ignore=tests/interactive

.PHONY: test-interactive
test-interactive:
	@echo "Running interactive PTY tests (may have file descriptor issues in some environments)..."
	@echo "Note: These tests may timeout or fail in certain CI environments due to PTY limitations"
	@uv run pytest tests/interactive -v --tb=short --maxfail=5

.PHONY: test-all
test-all:
	@echo "Running all tests (core + interactive)..."
	@echo "Warning: Interactive tests may fail in some environments due to PTY file descriptor issues"
	@uv run pytest

# MCP inspector
.PHONY: inspect
inspect:
	@MCP_SERVER_REQUEST_TIMEOUT=$(MCP_SERVER_REQUEST_TIMEOUT) \
		MCP_REQUEST_MAX_TOTAL_TIMEOUT=$(MCP_REQUEST_MAX_TOTAL_TIMEOUT) \
		npx @modelcontextprotocol/inspector@0.16.0 uv run openroad-mcp
