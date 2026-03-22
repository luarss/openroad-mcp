#!/usr/bin/env bash
# =============================================================================
# setup-ubuntu.sh — Install OpenROAD-MCP dependencies on Ubuntu (22.04/24.04)
# =============================================================================
set -euo pipefail

echo "🔧 Setting up OpenROAD-MCP on Ubuntu..."

# System dependencies
sudo apt-get update
sudo apt-get install -y \
    python3 python3-dev python3-venv \
    build-essential curl git

# Install uv (Python package manager)
if ! command -v uv &>/dev/null; then
    echo "📦 Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi

# Sync project
echo "📦 Installing project dependencies..."
uv sync --all-extras --inexact

echo ""
echo "✅ Ubuntu setup complete!"
echo ""
echo "Next steps:"
echo "  1. Install OpenROAD: https://openroad.readthedocs.io/en/latest/main/GettingStarted.html"
echo "  2. Run tests:        make test"
echo "  3. Start MCP server: uv run openroad-mcp"
