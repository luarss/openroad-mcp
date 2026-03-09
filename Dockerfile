ARG ORFS_VERSION=latest
ARG UV_VERSION=latest

# Stage 1: builder
# Both stages use openroad/orfs since OpenROAD binaries are required at
# runtime. Multi-stage still keeps uv and build artifacts out of the final image.
# Slimming the runtime by copying only specific binaries is a follow-up task.
FROM openroad/orfs:${ORFS_VERSION} AS builder

COPY --from=ghcr.io/astral-sh/uv:${UV_VERSION} /uv /usr/local/bin/uv

# The base image ships Python < 3.13, but the project requires >=3.13.
# Let uv download a managed Python, but redirect it to a portable directory
# (/opt/python) instead of the default /root/.local/share/uv/python so we
# can COPY it cleanly into the runtime stage.
ENV UV_PYTHON_INSTALL_DIR=/opt/python

WORKDIR /app

# Copy manifests before source so the dependency layer is cached independently.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Second sync installs the project itself once source is present.
# --no-editable ensures the package is installed into site-packages rather than
# symlinked to src/, so the source tree is not needed at runtime.
COPY src/ ./src/
COPY README.md ./
RUN uv sync --frozen --no-dev --no-editable


# Stage 2: runtime
ARG ORFS_VERSION=latest
FROM openroad/orfs:${ORFS_VERSION} AS runtime

# --no-log-init avoids sparse /var/log/lastlog issues in Docker.
RUN useradd --create-home --shell /bin/bash --uid 1000 --no-log-init appuser

WORKDIR /app

COPY --from=builder --chown=appuser:appuser /app/.venv /app/.venv
# Copy the uv-managed Python so the venv's symlinks resolve correctly.
COPY --from=builder --chown=appuser:appuser /opt/python /opt/python

USER appuser

ENV PATH="/app/.venv/bin:/OpenROAD-flow-scripts/tools/install/OpenROAD/bin:/OpenROAD-flow-scripts/tools/install/yosys/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    ORFS_FLOW_PATH=/OpenROAD-flow-scripts/flow

# Verify import works as appuser (same context as production runtime).
RUN /app/.venv/bin/python -c "import openroad_mcp"

ENTRYPOINT ["openroad-mcp"]