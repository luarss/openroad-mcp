# =============================================================================
# setup-wsl2.ps1 — Install OpenROAD-MCP dependencies on Windows via WSL2
# =============================================================================

Write-Host "🔧 Setting up OpenROAD-MCP on Windows via WSL2..." -ForegroundColor Cyan

# Check WSL2 is available
$wslVersion = wsl --status 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ WSL2 is not installed. Run: wsl --install" -ForegroundColor Red
    Write-Host "   Restart your computer after installation." -ForegroundColor Yellow
    exit 1
}

# Check for Ubuntu distribution
$distros = wsl --list --quiet 2>$null
if ($distros -notmatch "Ubuntu") {
    Write-Host "📦 Installing Ubuntu 24.04 in WSL2..."
    wsl --install -d Ubuntu-24.04
    Write-Host "⚠️  Please restart your terminal after Ubuntu finishes installing." -ForegroundColor Yellow
    exit 0
}

# Run the Ubuntu setup script inside WSL2
Write-Host "📦 Setting up inside WSL2..."
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectDir = Split-Path -Parent $scriptDir
$wslProjectDir = wsl -d Ubuntu-24.04 -- wslpath -a $projectDir

wsl -d Ubuntu-24.04 -- bash -c @"
    cd '$wslProjectDir'
    chmod +x scripts/setup-ubuntu.sh
    ./scripts/setup-ubuntu.sh
"@

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "✅ WSL2 setup complete!" -ForegroundColor Green
    Write-Host ""
    Write-Host "To use OpenROAD-MCP, open WSL2:" -ForegroundColor Cyan
    Write-Host "  wsl -d Ubuntu-24.04"
    Write-Host "  cd $wslProjectDir"
    Write-Host "  make test"
    Write-Host ""
    Write-Host "Optional: Install Docker Desktop for container support:" -ForegroundColor Cyan
    Write-Host "  https://docs.docker.com/desktop/install/windows-install/"
} else {
    Write-Host "❌ Setup failed inside WSL2." -ForegroundColor Red
    exit 1
}
