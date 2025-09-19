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
	@uv run pytest --ignore=tests/interactive --ignore=tests/performance

.PHONY: test-interactive
test-interactive:
	@echo "Running interactive PTY tests (may have file descriptor issues in some environments)..."
	@echo "Note: These tests may timeout or fail in certain CI environments due to PTY limitations"
	@uv run pytest tests/interactive -v --tb=short --maxfail=5

.PHONY: test-integration
test-integration:
	@echo "Running integration tests for timing workflows..."
	@uv run pytest tests/integration/test_timing_workflows.py -v --tb=short

.PHONY: test-tools
test-tools:
	@echo "Running MCP tools tests..."
	@uv run pytest tests/tools/ -v --tb=short

.PHONY: test-performance
test-performance:
	@echo "Running performance benchmark tests..."
	@uv run pytest tests/performance/test_benchmarks.py -v -s --tb=short

.PHONY: test-memory
test-memory:
	@echo "Running memory monitoring and leak detection tests..."
	@uv run pytest tests/performance/test_memory_monitoring.py -v -s --tb=short

.PHONY: test-stability
test-stability:
	@echo "Running stability simulation tests..."
	@uv run pytest tests/performance/test_memory_monitoring.py::TestStabilityMonitoring::test_stability_simulation -v -s --tb=short

.PHONY: test-all
test-all:
	@echo "Running all tests (core + interactive + performance)..."
	@echo "Warning: Interactive tests may fail in some environments due to PTY file descriptor issues"
	@uv run pytest

.PHONY: test-comprehensive
test-comprehensive:
	@echo "Running comprehensive test suite for TICKET-020..."
	@echo "1. Core tests..."
	@$(MAKE) test
	@echo "2. Interactive tests..."
	@$(MAKE) test-interactive
	@echo "3. Integration tests..."
	@$(MAKE) test-integration
	@echo "4. Tools tests..."
	@$(MAKE) test-tools
	@echo "5. Performance tests..."
	@$(MAKE) test-performance
	@echo "6. Memory tests..."
	@$(MAKE) test-memory
	@echo "All TICKET-020 test requirements completed!"

.PHONY: test-coverage
test-coverage:
	@echo "Running tests with coverage analysis..."
	@uv add pytest-cov
	@uv run pytest --cov=src/openroad_mcp --cov-report=xml --cov-report=html --cov-report=term-missing

# MCP inspector
.PHONY: inspect
inspect:
	@MCP_SERVER_REQUEST_TIMEOUT=$(MCP_SERVER_REQUEST_TIMEOUT) \
		MCP_REQUEST_MAX_TOTAL_TIMEOUT=$(MCP_REQUEST_MAX_TOTAL_TIMEOUT) \
		npx @modelcontextprotocol/inspector@0.16.0 uv run openroad-mcp
