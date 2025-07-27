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
	@ruff format .
	@ruff check . --fix

.PHONY: check
check:
	@ruff check
	@mypy .
	@pre-commit run --all-files

.PHONY: test
test:
	@pytest

# MCP inspector
.PHONY: inspect
inspect:
	@MCP_SERVER_REQUEST_TIMEOUT=$(MCP_SERVER_REQUEST_TIMEOUT) \
		MCP_REQUEST_MAX_TOTAL_TIMEOUT=$(MCP_REQUEST_MAX_TOTAL_TIMEOUT) \
		npx @modelcontextprotocol/inspector@0.16.0 uv run openroad-mcp
