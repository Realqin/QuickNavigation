# Export all Docker images for offline deployment (run on a machine with internet).
# Usage: powershell -ExecutionPolicy Bypass -File scripts/docker/export-offline.ps1
#
# Optional env:
#   DOCKER_MIRROR=docker.1ms.run   mirror host when Docker Hub is unstable

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$OutDir = Join-Path $Root "offline\docker-images"
$TarFile = Join-Path $OutDir "quicknav-images.tar"
$Manifest = Join-Path $OutDir "images.txt"
$MirrorHost = if ($env:DOCKER_MIRROR) { $env:DOCKER_MIRROR.TrimEnd('/') } else { "docker.1ms.run" }

function Clear-ProxyEnv {
    $names = @(
        "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY",
        "http_proxy", "https_proxy", "all_proxy", "no_proxy"
    )
    foreach ($name in $names) {
        if (Test-Path "Env:$name") {
            Remove-Item "Env:$name" -ErrorAction SilentlyContinue
        }
    }
}

function Test-DockerImage {
    param([string]$Image)
    & docker image inspect $Image 2>$null | Out-Null
    return ($LASTEXITCODE -eq 0)
}

function Get-MirrorRef {
    param([string]$Image)
    if ($Image -match '^[^/]+:[^/]+$') {
        return "$MirrorHost/library/$Image"
    }
    return "$MirrorHost/$Image"
}

function Show-DockerPullHint {
    param([string]$Image)
    Write-Host ""
    Write-Host "Failed to pull $Image. Try:"
    Write-Host "  1. Docker Desktop -> Settings -> Resources -> Proxies -> turn OFF manual proxy"
    Write-Host "  2. docker pull $Image"
    Write-Host "  3. docker pull $(Get-MirrorRef $Image) ; docker tag $(Get-MirrorRef $Image) $Image"
    Write-Host "  4. Set mirror: `$env:DOCKER_MIRROR='docker.1ms.run' then rerun this script"
    Write-Host ""
}

function Invoke-Docker {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$DockerArgs)
    & docker @DockerArgs
    if ($LASTEXITCODE -ne 0) {
        throw "docker $($DockerArgs -join ' ') failed (exit $LASTEXITCODE)"
    }
}

function Invoke-DockerPull {
    param([string]$Image, [int]$Retries = 3)

    if (Test-DockerImage $Image) {
        Write-Host "    skip $Image (already local)"
        return
    }

    for ($i = 1; $i -le $Retries; $i++) {
        Write-Host "    pull $Image (attempt $i/$Retries)"
        & docker pull $Image
        if ($LASTEXITCODE -eq 0) { return }
        if ($i -lt $Retries) {
            $waitSec = [Math]::Min(15, 2 * $i)
            Write-Host "    retry in ${waitSec}s ..."
            Start-Sleep -Seconds $waitSec
        }
    }

    $mirrorRef = Get-MirrorRef $Image
    if ($mirrorRef -ne $Image) {
        Write-Host "    try mirror: $mirrorRef"
        & docker pull $mirrorRef
        if ($LASTEXITCODE -eq 0) {
            & docker tag $mirrorRef $Image
            if ($LASTEXITCODE -eq 0) { return }
        }
    }

    Show-DockerPullHint -Image $Image
    throw "docker pull $Image failed (official + mirror)"
}

function Sync-LegacyImageTags {
    $pairs = @(
        @("quicknavigation-backend:latest", "quicknav-backend:latest"),
        @("quicknavigation-frontend:latest", "quicknav-frontend:latest")
    )
    foreach ($pair in $pairs) {
        $src = $pair[0]
        $dst = $pair[1]
        if (Test-DockerImage $dst) { continue }
        if (Test-DockerImage $src) {
            Write-Host "    tag $src -> $dst"
            & docker tag $src $dst
        }
    }
}

function Get-ComposeImages {
    return @(docker compose config --images | Sort-Object -Unique)
}

function Test-AllComposeImagesReady {
    foreach ($img in (Get-ComposeImages)) {
        if (-not (Test-DockerImage $img)) { return $false }
    }
    return $true
}

Clear-ProxyEnv
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
Set-Location $Root

$env:COMPOSE_PROJECT_NAME = "quicknav"
$env:DOCKER_BUILDKIT = "1"

Write-Host "==> Pulling remote images from compose..."
foreach ($img in @("mysql:8.0", "niruix/sshwifty:latest", "redis/redisinsight:latest")) {
    Invoke-DockerPull -Image $img
}

Write-Host "==> Pulling base images used by Dockerfiles..."
$baseImages = @(
    "provectuslabs/kafka-ui:v0.7.2",
    "python:3.12-slim-bookworm",
    "node:20-alpine",
    "nginx:1.27-alpine"
)
foreach ($img in $baseImages) {
    Invoke-DockerPull -Image $img
}

Sync-LegacyImageTags

if (Test-AllComposeImagesReady) {
    Write-Host "==> All compose images already local, skip build"
} else {
    Write-Host "==> Building missing project images..."
    $env:HTTP_PROXY = ""
    $env:HTTPS_PROXY = ""
    $env:ALL_PROXY = ""
    $env:http_proxy = ""
    $env:https_proxy = ""
    $env:all_proxy = ""
    Invoke-Docker -DockerArgs @("compose", "build", "--pull=false")
}

Write-Host "==> Collecting image list..."
$images = Get-ComposeImages
$images | Set-Content -Encoding utf8 $Manifest
Write-Host "    $($images.Count) images -> $Manifest"

$missing = @()
foreach ($img in $images) {
    if (-not (Test-DockerImage $img)) { $missing += $img }
}
if ($missing.Count -gt 0) {
    throw "Missing local images (build/pull incomplete):`n  - $($missing -join "`n  - ")"
}

Write-Host "==> Saving to $TarFile ..."
if (Test-Path $TarFile) { Remove-Item -Force $TarFile }
$saveArgs = @("save", "-o", $TarFile) + $images
Invoke-Docker -DockerArgs $saveArgs

$sizeMb = [math]::Round((Get-Item $TarFile).Length / 1MB, 1)
Write-Host ""
Write-Host "Done. Copy these to the target server:"
Write-Host "  - $TarFile  ($sizeMb MB)"
Write-Host "  - $Manifest"
Write-Host "  - project folder (docker-compose.yml + docker-compose.offline.yml)"
Write-Host ""
Write-Host "On target server, run:"
Write-Host "  powershell -ExecutionPolicy Bypass -File scripts/docker/import-offline.ps1"
