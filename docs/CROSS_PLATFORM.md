# Cross-Platform Guide — OpenROAD MCP

OpenROAD-MCP supports **Ubuntu**, **macOS**, and **Windows (via WSL2)**. This guide covers setup and known issues for each.

---

## Ubuntu (22.04 / 24.04)

### Automated Setup

```bash
chmod +x scripts/setup-ubuntu.sh
./scripts/setup-ubuntu.sh
```

### Manual Steps

```bash
# Install system dependencies
sudo apt-get update
sudo apt-get install -y python3 python3-dev python3-venv build-essential curl git

# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"

# Install OpenROAD (for integration tests)
# See: https://openroad.readthedocs.io/en/latest/main/GettingStarted.html

# Sync project
uv sync --all-extras --inexact
make test
```

---

## macOS

### Automated Setup

```bash
chmod +x scripts/setup-macos.sh
./scripts/setup-macos.sh
```

### Requirements

- **Homebrew** (https://brew.sh)
- **Python 3.13+** (`brew install python@3.13`)
- **Xcode CLI tools** (`xcode-select --install`)

### Known Issues

| Issue | Workaround |
|-------|-----------|
| OpenROAD not available via Homebrew | Use Docker: `docker compose up openroad-mcp` |
| PTY tests flaky on macOS CI | Run `make test` (core only); PTY tests are optional |
| `libomp` not found | `brew install libomp` |

---

## Windows (WSL2)

### Prerequisites

1. **Windows 10 (2004+) or Windows 11**
2. **WSL2 enabled**: `wsl --install`
3. **Ubuntu 24.04 in WSL2**: installed automatically by setup script

### Automated Setup

Run in PowerShell as Administrator:

```powershell
.\scripts\setup-wsl2.ps1
```

### Manual Steps

```powershell
# 1. Install WSL2 + Ubuntu
wsl --install -d Ubuntu-24.04

# 2. Open WSL2 terminal
wsl -d Ubuntu-24.04

# 3. Inside WSL2, run the Ubuntu setup
cd /mnt/c/path/to/openroad-mcp
chmod +x scripts/setup-ubuntu.sh
./scripts/setup-ubuntu.sh
```

### Docker Integration

For the best experience on Windows, install **Docker Desktop** with WSL2 backend:
- https://docs.docker.com/desktop/install/windows-install/
- Enable "Use the WSL 2 based engine" in Docker Desktop settings

Then use Docker Compose from WSL2:

```bash
docker compose up openroad-mcp
```

### Known Issues

| Issue | Workaround |
|-------|-----------|
| Path translation (`/mnt/c/` vs `C:\`) | Always work from inside WSL2, not from PowerShell |
| PTY behavior differs from Linux | If PTY tests fail, use Docker instead |
| File permissions issues | Run `chmod +x` on scripts after cloning in WSL2 |
| Slow I/O on `/mnt/c/` | Clone the repo inside WSL2's native filesystem (`~/openroad-mcp`) |

---

## Testing on Your Platform

```bash
# Core tests (no OpenROAD required)
make test

# Tools tests (no OpenROAD required)
make test-tools

# Interactive PTY tests (Docker recommended)
make test-interactive

# Integration tests (Docker required — uses OpenROAD/ORFS)
make test-integration
```

## MCP Client Compatibility

| Client | Status | Notes |
|--------|--------|-------|
| Local AI Assistant (e.g., Cursor) | ✅ Supported | Primary target |
| Gemini CLI | ✅ Supported | Follow Gemini MCP install guide |
| VS Code (MCP extension) | ✅ Supported | Configure in `.vscode/settings.json` |
| Zed | ✅ Supported | Configure in Zed settings |
