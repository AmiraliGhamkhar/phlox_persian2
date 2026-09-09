<#
.SYNOPSIS
    Build & run Phlox (phlox_persian2) with Docker on Windows 11.

.DESCRIPTION
    - Checks Docker Desktop is installed and running.
    - Creates .env from .env.example if missing and fills in a required
      DB_ENCRYPTION_KEY (64 hex chars) when absent; writes files as LF/ASCII
      so the compose file and SQLCipher key parsing never break on Windows.
      The key is ALSO saved to .phlox-encryption-key.txt in this folder -
      keep that file safe, it cannot be recovered later.
    - Starts the stack (builds the image locally by default).
    - Waits for the container healthcheck to pass, then opens the app.

.PARAMETER UsePublishedImage
    Run `docker compose pull` instead of `docker compose up -d --build`.

.PARAMETER Dev
    Use docker-compose.dev.yml (hot reload; UI http://localhost:3000).

.PARAMETER NoBrowser
    Do not open the browser automatically.

.EXAMPLE
    Set-ExecutionPolicy -Scope Process Bypass; .\run-on-windows.ps1
.EXAMPLE
    .\run-on-windows.ps1 -UsePublishedImage
#>
[CmdletBinding()]
param(
    [switch]$UsePublishedImage,
    [switch]$Dev,
    [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'

function Write-Step($msg)  { Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Write-Ok($msg)    { Write-Host "    $msg" -ForegroundColor Green }
function Write-Warn($msg)  { Write-Host "    WARN: $msg" -ForegroundColor Yellow }

# ---------------------------------------------------------------- checks ----
Write-Step "Checking prerequisites..."

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "Docker not found. Install Docker Desktop from https://docs.docker.com/desktop/install/windows/" -ForegroundColor Red
    exit 1
}
docker info *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host "The Docker daemon is not running. Start 'Docker Desktop' and wait for the whale icon to show 'Engine running'." -ForegroundColor Red
    exit 1
}
docker compose version *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host "'docker compose' (v2) is unavailable - update Docker Desktop." -ForegroundColor Red
    exit 1
}
if (-not (Test-Path .\docker-compose.yml)) {
    Write-Host "docker-compose.yml not found. Run this script from the repository root (cd phlox_persian2)." -ForegroundColor Red
    exit 1
}
Write-Ok "Docker is up and this is the Phlox repo root."

# ------------------------------------------------------------------- .env ----
Write-Step "Preparing .env (LF line endings + encryption key)..."

$envPath = Join-Path (Get-Location) '.env'
$keyFile = Join-Path (Get-Location) '.phlox-encryption-key.txt'

function New-EncryptionKey {
    $bytes = New-Object byte[] 32
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $rng.GetBytes($bytes)
    $rng.Dispose()
    return ([System.BitConverter]::ToString($bytes)).Replace('-', '').ToLower()
}

$utf8NoBom = New-Object System.Text.UTF8Encoding($false)

if (-not (Test-Path $envPath)) {
    if (-not (Test-Path .\.env.example)) {
        Write-Host "Missing .env.example - cannot create .env. Is this really the repository?" -ForegroundColor Red
        exit 1
    }
    Copy-Item .\.env.example $envPath
    Write-Ok "Created .env from .env.example"
}

$lines = [System.IO.File]::ReadAllLines($envPath)
$key = $null
$keyFound = $false
for ($i = 0; $i -lt $lines.Length; $i++) {
    if ($lines[$i] -match '^DB_ENCRYPTION_KEY=(.*)$') {
        $keyFound = $true
        $key = $Matches[1].Trim()
    }
}
if (-not $keyFound -or [string]::IsNullOrEmpty($key)) {
    $key = New-EncryptionKey
    if ($keyFound) {
        for ($i = 0; $i -lt $lines.Length; $i++) {
            if ($lines[$i] -match '^DB_ENCRYPTION_KEY=') { $lines[$i] = "DB_ENCRYPTION_KEY=$key" }
        }
    } else {
        $lines += "DB_ENCRYPTION_KEY=$key"
    }
    Write-Ok "Generated a fresh DB_ENCRYPTION_KEY"
    Write-Warn "Your encryption key was saved to: $keyFile"
    Write-Warn "Keep it safe: without it, the encrypted database can NEVER be reopened."
} else {
    Write-Ok "DB_ENCRYPTION_KEY is already set in .env (not modified)."
}

# Always rewrite .env with LF endings: a CRLF .env on Windows makes docker
# compose read the trailing \r as part of DB_ENCRYPTION_KEY, and that key can
# never be fixed later without losing access to the encrypted database.
$text = ($lines -join "`n") + "`n"
[System.IO.File]::WriteAllText($envPath, $text, $utf8NoBom)
if (-not [string]::IsNullOrEmpty($key)) {
    # Mirror the active key into the backup file (also covers pre-existing keys).
    [System.IO.File]::WriteAllText($keyFile, "Phlox DB_ENCRYPTION_KEY (keep safe - cannot be recovered):`n$key`n", $utf8NoBom)
    Write-Ok "Encryption key backed up to: $keyFile"
}

# -------------------------------------------------------------- compose -----
$composeFile = if ($Dev) { 'docker-compose.dev.yml' } else { 'docker-compose.yml' }
Write-Step "Starting stack: $composeFile"

if ($UsePublishedImage) {
    if ($Dev) { Write-Host "-UsePublishedImage is ignored in -Dev mode (dev image is always built locally)." -ForegroundColor Yellow }
    else {
        docker compose pull
        if ($LASTEXITCODE -ne 0) {
            Write-Host "Pulling the published image failed (it may not exist for this repo/tag)." -ForegroundColor Yellow
            Write-Host "Falling back to building the image from this repository..." -ForegroundColor Yellow
            docker compose up -d --build
        } else {
            docker compose up -d
        }
    }
} else {
    if ($Dev) {
        docker compose -f $composeFile up -d --build
    } else {
        docker compose up -d --build
    }
}
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

# ------------------------------------------------------------- wait/health ---
$container = if ($Dev) { 'phlox-dev' } else { 'phlox' }

Write-Step "Waiting for container '$container' to become healthy (up to ~5 min)..."

$healthy = $false
for ($i = 0; $i -lt 60; $i++) {
    Start-Sleep -Seconds 5
    $status = (& docker inspect -f "{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}" $container 2>$null)
    if ($LASTEXITCODE -ne 0) { continue }
    if ($status -eq 'healthy') { $healthy = $true; break }
    if ($status -eq 'unhealthy' -or $status -eq 'exited' -or $status -eq 'dead') {
        Write-Host "Container status: $status - recent logs:" -ForegroundColor Yellow
        if ($Dev) { docker compose -f $composeFile logs --tail=60 } else { docker compose logs --tail=60 }
        exit 1
    }
    Write-Host "  [$i/60] status: $status"
}
if (-not $healthy) {
    Write-Host "`nTimed out waiting for the healthcheck. Inspect logs with:" -ForegroundColor Yellow
    if ($Dev) { Write-Host "docker compose -f docker-compose.dev.yml logs -f" } else { Write-Host "docker compose logs -f" }
    Write-Host "Common cause: DB_ENCRYPTION_KEY mismatch with an existing volume (see WINDOWS_DOCKER_SETUP.md)."
    exit 1
}

Write-Ok "Container is healthy!"

# ------------------------------------------------------------------- done ----
Write-Host ""
Write-Host "Phlox is running:" -ForegroundColor Green
if ($Dev) {
    Write-Host "  UI : http://localhost:3000"
    Write-Host "  API: http://localhost:5000/docs"
} else {
    Write-Host "  UI : http://127.0.0.1:5000"
    Write-Host "  API: http://127.0.0.1:5000/docs"
}
Write-Host "Useful:"
if ($Dev) { Write-Host "  docker compose -f docker-compose.dev.yml logs -f" } else { Write-Host "  docker compose logs -f" }
Write-Host "  docker compose down    # stop (data volume phlox_data is kept)"
$url = if ($Dev) { 'http://localhost:3000' } else { 'http://127.0.0.1:5000' }
if (-not $NoBrowser) {
    Start-Sleep -Seconds 2
    Start-Process $url
}
