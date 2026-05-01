#Requires -Version 5.1
<#
.SYNOPSIS
    First-time setup for the Ollama + Open WebUI stack.
#>

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

function Write-Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Write-OK($msg)   { Write-Host "    OK: $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "    WARN: $msg" -ForegroundColor Yellow }
function Write-Fail($msg) { Write-Host "    ERROR: $msg" -ForegroundColor Red; exit 1 }

# --- 1. Check Docker is available and running ---
Write-Step "Checking Docker"
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Fail "Docker not found. Install Docker Desktop from https://www.docker.com/products/docker-desktop/"
}
try {
    docker info 2>&1 | Out-Null
    Write-OK "Docker is running"
} catch {
    Write-Fail "Docker is installed but not running. Start Docker Desktop and try again."
}

# --- 2. Create .env if missing ---
Write-Step "Checking .env"
$envFile = Join-Path $scriptDir ".env"
$envExample = Join-Path $scriptDir ".env.example"

if (-not (Test-Path $envFile)) {
    Copy-Item $envExample $envFile
    Write-Warn ".env created from .env.example — please set a real WEBUI_SECRET_KEY before continuing."
    Write-Warn "Edit $envFile then re-run this script."
    exit 0
}

$envContent = Get-Content $envFile -Raw
if ($envContent -match "change-this-to-a-random-string") {
    Write-Fail "WEBUI_SECRET_KEY is still the placeholder. Edit $envFile and set a real secret key."
}
Write-OK ".env looks good"

# --- 3. Start containers ---
Write-Step "Starting containers (docker compose up -d)"
Push-Location $scriptDir
docker compose up -d
if ($LASTEXITCODE -ne 0) { Write-Fail "docker compose up failed" }
Write-OK "Containers started"

# --- 4. Wait for Ollama to be ready ---
Write-Step "Waiting for Ollama to be ready"
$maxWait = 60
$waited  = 0
$ready   = $false
while ($waited -lt $maxWait) {
    try {
        $resp = Invoke-WebRequest -Uri "http://localhost:11434" -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
        if ($resp.StatusCode -eq 200) { $ready = $true; break }
    } catch {}
    Start-Sleep -Seconds 2
    $waited += 2
    Write-Host "    ... waiting ($waited s)" -ForegroundColor DarkGray
}
if (-not $ready) { Write-Fail "Ollama did not respond after $maxWait seconds. Check: docker logs ollama" }
Write-OK "Ollama is ready"

# --- 5. Pull model ---
Write-Step "Pulling llama3.1:8b (this will take a few minutes on first run)"
docker exec ollama ollama pull llama3.1:8b
if ($LASTEXITCODE -ne 0) { Write-Fail "Model pull failed" }
Write-OK "Model ready"

Pop-Location

# --- Done ---
Write-Host ""
Write-Host "==========================================" -ForegroundColor Green
Write-Host "  Setup complete!" -ForegroundColor Green
Write-Host "  Open WebUI: http://localhost:3000" -ForegroundColor Green
Write-Host ""
Write-Host "  To find your local IP for other devices:" -ForegroundColor White
Write-Host "    ipconfig | findstr 'IPv4'" -ForegroundColor DarkGray
Write-Host "  Then share: http://<your-IP>:3000" -ForegroundColor White
Write-Host "==========================================" -ForegroundColor Green
