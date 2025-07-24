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

.PHONY:
check:
	@ruff check
	@pre-commit run --all-files
 
# MCP inspector
.PHONY: inspect
inspect:
	@npx @modelcontextprotocol/inspector@0.16.0 uv run main.py
