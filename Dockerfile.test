# Test environment with OpenROAD for CI
FROM openroad/orfs:latest

# Install uv (will handle Python installation)
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# Set working directory
WORKDIR /app

# Copy project files
COPY . .

# Install dependencies
RUN uv sync --all-extras --inexact

# Set environment for tests
ENV PYTHONPATH=/app/src
ENV PATH="/app/.venv/bin:/OpenROAD-flow-scripts/tools/install/OpenROAD/bin:/OpenROAD-flow-scripts/tools/install/yosys/bin:$PATH"

# Default command
CMD ["bash"]
