# Use OpenROAD's official Ubuntu 22.04 development image
FROM openroad/ubuntu22.04-dev:latest

# Set working directory
WORKDIR /app

# Install Python 3.13 and uv package manager
RUN apt-get update && apt-get install -y \
    software-properties-common \
    curl \
    && add-apt-repository ppa:deadsnakes/ppa \
    && apt-get update \
    && apt-get install -y \
    python3.13 \
    python3.13-dev \
    python3.13-venv \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

# Install uv package manager
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.cargo/bin:$PATH"

# Copy project files
COPY . .

# Install Python dependencies using uv
RUN uv sync --all-extras --inexact

# Set environment variables for MCP server timeouts
ENV MCP_SERVER_REQUEST_TIMEOUT=99999999999
ENV MCP_REQUEST_MAX_TOTAL_TIMEOUT=99999999999

# Expose the default port (if using HTTP transport in the future)
EXPOSE 8000

# Default command to run the MCP server
CMD ["uv", "run", "openroad-mcp"]
