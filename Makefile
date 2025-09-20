MCP_SERVER_REQUEST_TIMEOUT:= 99999999999
MCP_REQUEST_MAX_TOTAL_TIMEOUT:= 99999999999
DOCKER_TEST_IMAGE:= openroad-mcp-test

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

# Build Docker test image
.PHONY: docker-test-build
docker-test-build:
	@docker build -f Dockerfile.test -t $(DOCKER_TEST_IMAGE) .

.PHONY: test-interactive
test-interactive: docker-test-build
	@echo "Running interactive tests..."
	@docker run --rm $(DOCKER_TEST_IMAGE) uv run pytest tests/interactive

.PHONY: test-integration
test-integration: docker-test-build
	@echo "Running integration tests for timing workflows..."
	@docker run --rm $(DOCKER_TEST_IMAGE) uv run pytest tests/integration/test_timing_workflows.py

.PHONY: test-tools
test-tools:
	@echo "Running MCP tools tests..."
	@uv run pytest tests/tools/

.PHONY: test-performance
test-performance: docker-test-build
	@echo "Running performance tests (benchmarks, memory, stability)..."
	@docker run --rm $(DOCKER_TEST_IMAGE) uv run pytest tests/performance/

.PHONY: test-coverage
test-coverage: docker-test-build
	@echo "Running tests with coverage analysis..."
	@docker run --rm $(DOCKER_TEST_IMAGE) uv run pytest --ignore=tests/performance --cov=src/openroad_mcp --cov-report=xml --cov-report=html --cov-report=term-missing

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
