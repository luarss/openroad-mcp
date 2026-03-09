ARG ORFS_VERSION=latest
ARG ORFS_DIGEST=sha256:e360317c5c9688a7093e89b7a0406a6cf19d72f3ba852365cc68ecfe5fb60a07
ARG UV_VERSION=latest
ARG UV_DIGEST=sha256:10902f58a1606787602f303954cea099626a4adb02acbac4c69920fe9d278f82

FROM ghcr.io/astral-sh/uv:${UV_VERSION}@${UV_DIGEST} AS uv

# Stage 1: builder - installs deps, discarded from final image.
# Both stages share openroad/orfs because OpenROAD binaries are needed at runtime.
FROM openroad/orfs:${ORFS_VERSION}@${ORFS_DIGEST} AS builder

COPY --from=uv /uv /usr/local/bin/uv

ENV UV_PYTHON_INSTALL_DIR=/opt/python

WORKDIR /app

# Manifests first — dependency layer is cached independently of source changes.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# --no-editable installs into site-packages; source tree not needed at runtime.
COPY src/ ./src/
COPY README.md ./
RUN uv sync --frozen --no-dev --no-editable


# Stage 2: runtime
ARG ORFS_VERSION=latest
ARG ORFS_DIGEST=sha256:e360317c5c9688a7093e89b7a0406a6cf19d72f3ba852365cc68ecfe5fb60a07
FROM openroad/orfs:${ORFS_VERSION}@${ORFS_DIGEST} AS runtime

RUN useradd --create-home --shell /bin/bash --uid 1000 --no-log-init appuser

WORKDIR /app

COPY --from=builder --chown=appuser:appuser /app/.venv /app/.venv
COPY --from=builder --chown=appuser:appuser /opt/python /opt/python

USER appuser

ENV PATH="/app/.venv/bin:/OpenROAD-flow-scripts/tools/install/OpenROAD/bin:/OpenROAD-flow-scripts/tools/install/yosys/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    ORFS_FLOW_PATH=/OpenROAD-flow-scripts/flow

# Verify non-editable install, console script, and ORFS path are all functional.
RUN /app/.venv/bin/python -c "import openroad_mcp; print(openroad_mcp.__file__)" && \
    openroad-mcp --help > /dev/null && \
    test -d "${ORFS_FLOW_PATH}" || (echo "ERROR: ORFS_FLOW_PATH=${ORFS_FLOW_PATH} not found" && exit 1)

ENTRYPOINT ["openroad-mcp"]