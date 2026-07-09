# Shared docker pull helpers (mirror + optional proxy).
# Dot-source from export-offline.ps1 / export-arm64.ps1

function Initialize-DockerNetworkEnv {
    if ($env:USE_PROXY -eq '1') {
        $proxy = if ($env:HTTP_PROXY) { $env:HTTP_PROXY } else { 'http://127.0.0.1:10808' }
        $env:HTTP_PROXY = $proxy
        $env:HTTPS_PROXY = if ($env:HTTPS_PROXY) { $env:HTTPS_PROXY } else { $proxy }
        $env:NO_PROXY = 'localhost,127.0.0.1'
        Write-Host "Proxy enabled: $proxy"
        Write-Host "Tip: also set Docker Desktop -> Settings -> Proxies if daemon pull still fails"
        return
    }
    foreach ($name in @('HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','http_proxy','https_proxy','all_proxy')) {
        if (Test-Path "Env:$name") {
            Remove-Item "Env:$name" -ErrorAction SilentlyContinue
        }
    }
}

function Get-DockerMirrorHosts {
    if ($env:DOCKER_MIRROR) {
        return @($env:DOCKER_MIRROR.TrimEnd('/'))
    }
    # daocloud works without proxy in CN; 1ms.run may follow broken system proxy
    return @('docker.m.daocloud.io', 'docker.1ms.run', 'dockerproxy.com')
}

function Get-MirrorRef {
    param(
        [string]$Image,
        [string]$MirrorHost
    )
    # Custom registry (docker.redpanda.com/...) has no CN mirror
    if ($Image -match '^[^/]+\.[^/]+/') {
        return $null
    }
    if ($Image -match '^[^/]+:[^/]+$') {
        return "$MirrorHost/library/$Image"
    }
    return "$MirrorHost/$Image"
}

function Test-DockerImage {
    param([string]$Image)
    $old = $ErrorActionPreference
    $ErrorActionPreference = 'SilentlyContinue'
    & docker image inspect $Image *> $null
    $ok = ($LASTEXITCODE -eq 0)
    $ErrorActionPreference = $old
    return $ok
}

function Get-ImageArch {
    param([string]$Image)
    if (-not (Test-DockerImage $Image)) { return $null }
    $old = $ErrorActionPreference
    $ErrorActionPreference = 'SilentlyContinue'
    $arch = & docker image inspect $Image --format '{{.Architecture}}' 2>$null
    $ErrorActionPreference = $old
    if ($LASTEXITCODE -ne 0) { return $null }
    return $arch
}

function Invoke-Docker {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$DockerArgs)
    & docker @DockerArgs
    if ($LASTEXITCODE -ne 0) {
        throw "docker $($DockerArgs -join ' ') failed (exit $LASTEXITCODE)"
    }
}

function Get-Arm64Digest {
    param(
        [string]$Image,
        [string[]]$MirrorHosts = @()
    )
    $refs = @($Image)
    foreach ($hostName in $MirrorHosts) {
        $ref = Get-MirrorRef -Image $Image -MirrorHost $hostName
        if ($ref) { $refs += $ref }
    }

    foreach ($ref in $refs) {
        $old = $ErrorActionPreference
        $ErrorActionPreference = 'SilentlyContinue'
        $raw = & docker buildx imagetools inspect $ref --raw 2>$null
        $ErrorActionPreference = $old
        if ($LASTEXITCODE -ne 0 -or -not $raw) { continue }
        try {
            $index = $raw | ConvertFrom-Json
            foreach ($item in $index.manifests) {
                if ($item.platform.architecture -eq 'arm64' -and $item.platform.os -eq 'linux') {
                    return @{ Digest = $item.digest; Source = $ref }
                }
            }
        } catch {
            continue
        }
    }
    return $null
}

function Invoke-DockerPullOnce {
    param(
        [string[]]$PullArgs,
        [string]$Label
    )
    Write-Host "    pull $Label"
    $old = $ErrorActionPreference
    $ErrorActionPreference = 'SilentlyContinue'
    # Do NOT pipe to Out-Null — it breaks $LASTEXITCODE for native commands
    $null = & docker pull @PullArgs 2>&1
    $ok = ($LASTEXITCODE -eq 0)
    $ErrorActionPreference = $old
    return $ok
}

function Use-ExistingMirrorImage {
    param(
        [string]$Image,
        [string[]]$MirrorHosts
    )
    foreach ($hostName in $MirrorHosts) {
        $ref = Get-MirrorRef -Image $Image -MirrorHost $hostName
        if (-not $ref) { continue }
        if (Test-DockerImage $ref) {
            $old = $ErrorActionPreference
            $ErrorActionPreference = 'SilentlyContinue'
            & docker tag $ref $Image 2>$null
            $ErrorActionPreference = $old
            if (Test-DockerImage $Image) {
                $arch = Get-ImageArch $Image
                Write-Host "    reuse local $ref -> $Image ($arch)"
                return $true
            }
        }
    }
    return $false
}

function Invoke-DockerPullWithFallback {
    param(
        [string]$Image,
        [string]$Platform = '',
        [int]$Retries = 2,
        [switch]$AllowAmd64Fallback
    )

    $wantArch = if ($Platform) { $Platform -replace '^linux/', '' } else { $null }
    if ($AllowAmd64Fallback -and (Test-DockerImage $Image)) {
        $localArch = Get-ImageArch $Image
        if ($localArch) {
            Write-Host "    skip $Image (local $localArch)"
            return
        }
    }
    if ($wantArch) {
        $arch = Get-ImageArch $Image
        if ($arch -eq $wantArch) {
            Write-Host "    skip $Image ($arch)"
            return
        }
    } elseif (Test-DockerImage $Image) {
        Write-Host "    skip $Image (local)"
        return
    }

    $platformArgs = @()
    if ($Platform) { $platformArgs = @('--platform', $Platform) }

    $mirrorHosts = Get-DockerMirrorHosts
    $attempts = @()
    foreach ($hostName in $mirrorHosts) {
        $ref = Get-MirrorRef -Image $Image -MirrorHost $hostName
        if ($ref) {
            $attempts += @{ Label = "$Image via $hostName"; Ref = $ref }
        }
    }
    # Official registry last (often blocked in CN without proxy)
    $attempts += @{ Label = "$Image (official)"; Ref = $Image }

    foreach ($attempt in $attempts) {
        for ($i = 1; $i -le $Retries; $i++) {
            if ($i -gt 1) { Write-Host "      retry $i/$Retries ..." }
            if (Invoke-DockerPullOnce -PullArgs ($platformArgs + $attempt.Ref) -Label $attempt.Label) {
                if ($attempt.Ref -ne $Image) {
                    & docker tag $attempt.Ref $Image 2>$null
                    if ($LASTEXITCODE -ne 0) {
                        & docker tag $attempt.Ref.Split('@')[0] $Image 2>$null
                    }
                }
                $arch = Get-ImageArch $Image
                if (-not $wantArch -or $arch -eq $wantArch) {
                    Write-Host "      ok -> $Image ($arch)"
                    return
                }
                Write-Host "      wrong arch $arch, expected $wantArch"
                & docker rmi $Image 2>$null | Out-Null
                break
            }
            if ($i -lt $Retries) { Start-Sleep -Seconds (2 * $i) }
        }
    }

    if ($wantArch -eq 'arm64') {
        $resolved = Get-Arm64Digest -Image $Image -MirrorHosts $mirrorHosts
        if ($resolved) {
            $digest = $resolved.Digest
            Write-Host "    resolve arm64 digest from $($resolved.Source)"
            foreach ($hostName in $mirrorHosts) {
                $base = Get-MirrorRef -Image $Image -MirrorHost $hostName
                if (-not $base) { continue }
                $repo = if ($base -match '^(.*):[^/]+$') { $Matches[1] } else { $base }
                $atRef = "$repo@$digest"
                if (Invoke-DockerPullOnce -PullArgs @($atRef) -Label "$Image@$digest via $hostName") {
                    $old = $ErrorActionPreference
                    $ErrorActionPreference = 'SilentlyContinue'
                    $tagged = $false
                    foreach ($src in @($atRef, "$repo@$digest", $ref)) {
                        if (-not (Test-DockerImage $src)) { continue }
                        & docker tag $src $Image 2>$null
                        if (Test-DockerImage $Image) { $tagged = $true; break }
                    }
                    $ErrorActionPreference = $old
                    if ($tagged) {
                        $arch = Get-ImageArch $Image
                        if ($arch -eq 'arm64') {
                            Write-Host "      ok -> $Image (arm64 via digest)"
                            return
                        }
                        Write-Host "      digest pulled but arch=$arch"
                    }
                }
            }
        }
    }

    if ($AllowAmd64Fallback) {
        Write-Host "    warn: no arm64 manifest, trying amd64 fallback for $Image"
        if (Use-ExistingMirrorImage -Image $Image -MirrorHosts $mirrorHosts) {
            Write-Host "      ok -> $Image (amd64 only, may need qemu on ARM server)"
            return
        }
        foreach ($hostName in $mirrorHosts) {
            $ref = Get-MirrorRef -Image $Image -MirrorHost $hostName
            if (-not $ref) { continue }
            if (Invoke-DockerPullOnce -PullArgs @($ref) -Label "$Image amd64 via $hostName") {
                $old = $ErrorActionPreference
                $ErrorActionPreference = 'SilentlyContinue'
                & docker tag $ref $Image 2>$null
                $ErrorActionPreference = $old
                if (Test-DockerImage $Image) {
                    Write-Host "      ok -> $Image (amd64 only, may need qemu on ARM server)"
                    return
                }
            }
        }
        if (Invoke-DockerPullOnce -PullArgs @($Image) -Label "$Image amd64 (official)") {
            if (Test-DockerImage $Image) {
                Write-Host "      ok -> $Image (amd64 only)"
                return
            }
        }
    }

    $mirrors = ($mirrorHosts | ForEach-Object { Get-MirrorRef -Image $Image -MirrorHost $_ } | Where-Object { $_ }) -join "`n    "
    throw @"
Failed to pull $Image

Root cause is usually ONE of:
  1. Docker Desktop proxy points to dead port 10808 -> disable Settings -> Proxies
  2. Windows system proxy enabled but Clash/V2Ray not running -> start proxy or disable system proxy
  3. docker.1ms.run blocked -> script now tries daocloud first

Try manually:
  docker pull docker.m.daocloud.io/library/mysql:8.0
  docker tag docker.m.daocloud.io/library/mysql:8.0 mysql:8.0

For arm64:
  `$env:DOCKER_MIRROR='docker.m.daocloud.io'
  powershell -File scripts/docker/export-arm64.ps1

Mirrors tried:
    $mirrors
"@
}
