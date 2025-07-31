# Use OpenROAD's ORFS image
FROM openroad/orfs:latest

# Set working directory
WORKDIR /app

# Install uv package manager
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# Verify uv installation
RUN /root/.local/bin/uv --version

# Copy project files
COPY . .

# Install Python dependencies using uv
RUN /root/.local/bin/uv sync --all-extras --inexact

# Set environment variables for MCP server timeouts
ENV MCP_SERVER_REQUEST_TIMEOUT=99999999999
ENV MCP_REQUEST_MAX_TOTAL_TIMEOUT=99999999999

# Expose the default port (if using HTTP transport in the future)
EXPOSE 8000

# Default command to run the MCP server
CMD ["/root/.local/bin/uv", "run", "openroad-mcp"]
