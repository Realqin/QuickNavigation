# Build and export Docker images for linux/arm64 (Kylin aarch64 servers).
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File scripts/docker/export-arm64.ps1
#
# Optional env:
#   USE_PROXY=1                          use local proxy (only if Clash/V2Ray is running)
#   HTTP_PROXY=http://127.0.0.1:7890     custom proxy port
#   DOCKER_MIRROR=docker.m.daocloud.io   default mirror (daocloud works without proxy)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$OutDir = Join-Path $Root "offline\docker-images"
$TarFile = Join-Path $OutDir "quicknav-images-arm64.tar"
$Manifest = Join-Path $OutDir "images-arm64.txt"

. (Join-Path $PSScriptRoot "docker-pull-common.ps1")

Initialize-DockerNetworkEnv
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
Set-Location $Root

$env:COMPOSE_PROJECT_NAME = "quicknav"
$env:DOCKER_DEFAULT_PLATFORM = "linux/arm64"
$env:DOCKER_BUILDKIT = "1"

# Images without arm64 — removed; OmniDB built from source, Kafka uses kafka-ui arm64
$Amd64FallbackImages = @()

Write-Host "==> Pulling arm64 base images (mirror -> digest fallback)..."
foreach ($img in @(
    "mysql:8.0",
    "niruix/sshwifty:latest",
    "redis/redisinsight:latest",
    "provectuslabs/kafka-ui:v0.7.2",
    "nginx:latest",
    "python:3.12-slim-bookworm",
    "node:20-alpine",
    "nginx:1.27-alpine"
)) {
    Invoke-DockerPullWithFallback -Image $img -Platform "linux/arm64" -AllowAmd64Fallback:($Amd64FallbackImages -contains $img)
}

Write-Host "==> Building project images (use local base tags, no registry pull)..."
Remove-Item Env:DOCKER_DEFAULT_PLATFORM -ErrorAction SilentlyContinue
Invoke-Docker -DockerArgs @("compose", "build", "--pull=false")

$images = @(docker compose config --images | Sort-Object -Unique)
$images | Set-Content -Encoding utf8 $Manifest

foreach ($img in $images) {
    $arch = Get-ImageArch $img
    if ($arch -eq 'arm64') { continue }
    if ($arch -eq 'amd64' -and ($img -like '*omnidb*' -or $img -like '*redpanda*' -or $img -like '*kafka-ui*')) {
        Write-Host "    warn: $img is amd64 (expected arm64 native build)"
        continue
    }
    throw "Image $img is $arch, expected arm64."
}

Write-Host "==> Saving $TarFile ..."
if (Test-Path $TarFile) { Remove-Item -Force $TarFile }
$saveArgs = @("save", "-o", $TarFile) + $images
Invoke-Docker -DockerArgs $saveArgs

$sizeMb = [math]::Round((Get-Item $TarFile).Length / 1MB, 1)
Write-Host "Done: $TarFile ($sizeMb MB)"
