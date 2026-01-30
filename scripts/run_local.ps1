$ErrorActionPreference='Stop'
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
$OutputEncoding = $utf8NoBom
[Console]::OutputEncoding = $utf8NoBom


$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Resolve-Path (Join-Path $scriptDir '..')

$envFile = Join-Path $projectRoot '.env'
if (-not (Test-Path $envFile)) {
    Write-Host "No .env found. Creating from .env.example"
    Copy-Item (Join-Path $projectRoot '.env.example') $envFile
}

Write-Host "Starting services..."
Set-Location $projectRoot

# Clean Docker build cache to avoid snapshot errors
Write-Host "Cleaning Docker build cache..."
try {
    docker compose down --remove-orphans | Out-Null
    docker builder prune -af | Out-Null
} catch {
    Write-Host "WARN: cache cleanup failed: $($_.Exception.Message)" -ForegroundColor Yellow
}

# Use local env file if present
if (Test-Path (Join-Path $projectRoot 'scripts\local_env.ps1')) {
    Write-Host "Sourcing scripts/local_env.ps1"
    . (Join-Path $projectRoot 'scripts\local_env.ps1')
}

try {
    docker compose build --no-cache
    docker compose up
} catch {
    Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
} finally {
    Write-Host ""
    Write-Host "Press Enter to close..."
    Read-Host | Out-Null
}
