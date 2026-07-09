# Import images and start stack on an offline server.
# Usage: powershell -ExecutionPolicy Bypass -File scripts/docker/import-offline.ps1

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$TarFile = Join-Path $Root "offline\docker-images\quicknav-images.tar"

if (-not (Test-Path $TarFile)) {
    Write-Error "Missing $TarFile. Run export-offline.ps1 on a machine with internet first."
}

Set-Location $Root
$env:COMPOSE_PROJECT_NAME = "quicknav"

Write-Host "==> Loading images..."
docker load -i $TarFile

Write-Host "==> Starting (no pull, no build)..."
docker compose -f docker-compose.yml -f docker-compose.offline.yml up -d --no-build

Write-Host ""
Write-Host "Started. Open http://<server-ip>:8080"
