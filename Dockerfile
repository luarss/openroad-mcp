# ---------- Stage 1: builder ----------
# Use OpenROAD image because MCP interacts with OpenROAD flows
FROM openroad/orfs:latest AS builder

# Install uv (fast Python dependency manager)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Store uv-managed Python in a portable location
ENV UV_PYTHON_INSTALL_DIR=/opt/python

WORKDIR /app

# Copy dependency manifests first (better Docker layer caching)
COPY pyproject.toml uv.lock ./

# Install dependencies without project source
RUN uv sync --frozen --no-dev --no-install-project

# Now copy project source
COPY src/ ./src
COPY README.md ./

# Install the project itself
RUN uv sync --frozen --no-dev


# ---------- Stage 2: runtime ----------
FROM openroad/orfs:latest AS runtime

# Create non-root runtime user
RUN useradd --create-home --shell /bin/bash --uid 1000 --no-log-init appuser

WORKDIR /app

# Copy virtual environment and source from builder
COPY --from=builder --chown=appuser:appuser /app/.venv /app/.venv
COPY --from=builder --chown=appuser:appuser /app/src /app/src
COPY --from=builder --chown=appuser:appuser /opt/python /opt/python

# Switch to non-root user
USER appuser

# Runtime environment
ENV PYTHONPATH=/app/src \
    PATH="/app/.venv/bin:/OpenROAD-flow-scripts/tools/install/OpenROAD/bin:/OpenROAD-flow-scripts/tools/install/yosys/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Verify runtime works
RUN /app/.venv/bin/python -c "import openroad_mcp"

# Healthcheck for container orchestration systems
HEALTHCHECK --interval=30s --timeout=5s \
  CMD openroad-mcp --help || exit 1

# OCI metadata (good container practice)
LABEL org.opencontainers.image.source="https://github.com/luarss/openroad-mcp"
LABEL org.opencontainers.image.description="OpenROAD MCP server container"
LABEL org.opencontainers.image.licenses="Apache-2.0"

# Default command
ENTRYPOINT ["openroad-mcp"]
