#Requires -Version 5.1
$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$VendorDir = Join-Path $Root "docker\omnidb\vendor"
$TarFile = Join-Path $VendorDir "OmniDB-3.0.3b.tar.gz"
$Version = "3.0.3b"

New-Item -ItemType Directory -Force -Path $VendorDir | Out-Null

if ((Test-Path $TarFile) -and ((Get-Item $TarFile).Length -gt 100000)) {
    Write-Host "Already exists: $TarFile"
    exit 0
}

$urls = @(
    "https://github.com/OmniDB/OmniDB/archive/$Version.tar.gz",
    "https://ghproxy.net/https://github.com/OmniDB/OmniDB/archive/$Version.tar.gz",
    "https://mirror.ghproxy.com/https://github.com/OmniDB/OmniDB/archive/$Version.tar.gz"
)

foreach ($url in $urls) {
    Write-Host "Downloading $url ..."
    try {
        Invoke-WebRequest -Uri $url -OutFile $TarFile -UseBasicParsing -TimeoutSec 120
        if ((Get-Item $TarFile).Length -gt 100000) {
            Write-Host "Saved: $TarFile"
            exit 0
        }
    } catch {
        Write-Host "Failed: $_"
    }
}

Remove-Item -Force $TarFile -ErrorAction SilentlyContinue
throw "Could not download OmniDB $Version source. Copy OmniDB-$Version.tar.gz manually into docker/omnidb/vendor/"
