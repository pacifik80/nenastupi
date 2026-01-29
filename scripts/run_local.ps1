$ErrorActionPreference='Stop'

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Resolve-Path (Join-Path $scriptDir '..')

$envFile = Join-Path $projectRoot '.env'
if (-not (Test-Path $envFile)) {
    Write-Host "No .env found. Creating from .env.example"
    Copy-Item (Join-Path $projectRoot '.env.example') $envFile
}

Write-Host "Starting services..."
Set-Location $projectRoot

# Use local env file if present
if (Test-Path (Join-Path $projectRoot 'scripts\local_env.ps1')) {
    Write-Host "Sourcing scripts/local_env.ps1"
    . (Join-Path $projectRoot 'scripts\local_env.ps1')
}

docker compose up --build
