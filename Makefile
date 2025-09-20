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
	@echo "Running core tests..."
	@uv run pytest --ignore=tests/interactive --ignore=tests/performance --ignore=tests/integration

.PHONY: test-interactive
test-interactive:
	@echo "Running interactive tests..."
	@docker build -f Dockerfile.test -t openroad-mcp-test .
	@docker run --rm openroad-mcp-test uv run pytest tests/interactive

.PHONY: test-integration
test-integration:
	@echo "Running integration tests for timing workflows..."
	@docker build -f Dockerfile.test -t openroad-mcp-test .
	@docker run --rm openroad-mcp-test uv run pytest tests/integration/test_timing_workflows.py

.PHONY: test-tools
test-tools:
	@echo "Running MCP tools tests..."
	@uv run pytest tests/tools/

.PHONY: test-performance
test-performance:
	@echo "Running performance tests (benchmarks, memory, stability)..."
	@docker build -f Dockerfile.test -t openroad-mcp-test .
	@docker run --rm openroad-mcp-test uv run pytest tests/performance/

.PHONY: test-coverage
test-coverage:
	@echo "Running tests with coverage analysis..."
	@uv run pytest --ignore=tests/performance --cov=src/openroad_mcp --cov-report=xml --cov-report=html --cov-report=term-missing

# MCP
.PHONY: inspect
inspect:
	@MCP_SERVER_REQUEST_TIMEOUT=$(MCP_SERVER_REQUEST_TIMEOUT) \
		MCP_REQUEST_MAX_TOTAL_TIMEOUT=$(MCP_REQUEST_MAX_TOTAL_TIMEOUT) \
		npx @modelcontextprotocol/inspector@0.16.0 uv run openroad-mcp

.PHONY: test-all
test-all:
	@echo "Running all tests (core + interactive + tools + integration)..."
	@$(MAKE) test
	@$(MAKE) test-interactive
	@$(MAKE) test-tools
	@$(MAKE) test-integration

.PHONY: mcp-json
mcp-json:
	@uv run fastmcp install mcp-json claude_code_server.py > mcp.json
