#!/usr/bin/env bash
# =============================================================================
# setup-macos.sh — Install OpenROAD-MCP dependencies on macOS
# =============================================================================
set -euo pipefail

echo "🔧 Setting up OpenROAD-MCP on macOS..."

# Check for Homebrew
if ! command -v brew &>/dev/null; then
    echo "❌ Homebrew is required. Install from: https://brew.sh"
    exit 1
fi

# Install Python 3.13+ if needed
if ! python3 --version 2>/dev/null | grep -qE "3\.(1[3-9]|[2-9][0-9])"; then
    echo "📦 Installing Python 3.13..."
    brew install python@3.13
fi

# Install uv
if ! command -v uv &>/dev/null; then
    echo "📦 Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi

# Sync project
echo "📦 Installing project dependencies..."
uv sync --all-extras --inexact

echo ""
echo "✅ macOS setup complete!"
echo ""
echo "Next steps:"
echo "  1. Install OpenROAD (optional, for full flows):"
echo "     See: https://openroad.readthedocs.io/en/latest/main/GettingStarted.html"
echo "  2. Or use Docker:    docker compose up openroad-mcp"
echo "  3. Run tests:        make test"
echo "  4. Start MCP server: uv run openroad-mcp"
