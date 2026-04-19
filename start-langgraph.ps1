# start-langgraph.ps1 - Start langgraph dev with LangSmith tracing env vars
#
# Usage:
#   .\start-langgraph.ps1                # default: --no-reload
#   .\start-langgraph.ps1 -NoReload:$false  # without --no-reload
#   .\start-langgraph.ps1 -Check         # check server status only

param(
    [switch]$NoReload = $true,
    [switch]$Check = $false
)

$ErrorActionPreference = "Stop"

# -- 1. Activate venv --
$VenvActivate = Join-Path $PSScriptRoot ".venv\Scripts\Activate.ps1"
if (Test-Path $VenvActivate) {
    . $VenvActivate
    Write-Host "[OK] venv activated" -ForegroundColor Green
} else {
    Write-Host "[WARN] .venv not found, using system Python" -ForegroundColor Yellow
}

# -- 2. Read LangSmith config from .env --
$EnvFile = Join-Path $PSScriptRoot ".env"
if (-not (Test-Path $EnvFile)) {
    Write-Host "[ERROR] .env file not found: $EnvFile" -ForegroundColor Red
    exit 1
}

function Get-DotEnvValue {
    param([string]$Key, [string[]]$Lines)
    foreach ($line in $Lines) {
        if ($line -match '^\s*#' -or $line -match '^\s*$') { continue }
        if ($line -match "^\s*$Key\s*=\s*(.+)$") {
            $val = $Matches[1].Trim()
            if (($val.StartsWith('"') -and $val.EndsWith('"')) -or
                ($val.StartsWith("'") -and $val.EndsWith("'"))) {
                $val = $val.Substring(1, $val.Length - 2)
            }
            return $val
        }
    }
    return $null
}

$envLines = Get-Content $EnvFile

$apiKeyVal   = Get-DotEnvValue -Key "LANGSMITH_API_KEY"    -Lines $envLines
$endpointVal = Get-DotEnvValue -Key "LANGSMITH_ENDPOINT"   -Lines $envLines
$projectVal  = Get-DotEnvValue -Key "LANGSMITH_PROJECT"    -Lines $envLines
$batchLimit  = Get-DotEnvValue -Key "LANGSMITH_BATCH_INGEST_SIZE_LIMIT" -Lines $envLines

# -- 3. Set env vars (child process langgraph dev will inherit) --
# Use LANGSMITH_TRACING_V2 (highest priority in langsmith SDK)
$env:LANGSMITH_TRACING_V2 = "true"
$env:LANGSMITH_TRACING = "true"

if ($apiKeyVal) {
    $env:LANGSMITH_API_KEY = $apiKeyVal
    $keyPreview = $apiKeyVal.Substring(0, [Math]::Min(20, $apiKeyVal.Length))
    Write-Host "[OK] LANGSMITH_API_KEY: ${keyPreview}..." -ForegroundColor Green
} else {
    Write-Host "[WARN] LANGSMITH_API_KEY not found in .env" -ForegroundColor Yellow
}

if ($endpointVal) {
    $env:LANGSMITH_ENDPOINT = $endpointVal
    Write-Host "[OK] LANGSMITH_ENDPOINT: $endpointVal" -ForegroundColor Green
} else {
    Write-Host "[INFO] LANGSMITH_ENDPOINT not set, using default (US)" -ForegroundColor Cyan
}

if ($projectVal) {
    $env:LANGSMITH_PROJECT = $projectVal
    Write-Host "[OK] LANGSMITH_PROJECT: $projectVal" -ForegroundColor Green
}

if ($batchLimit) {
    $env:LANGSMITH_BATCH_INGEST_SIZE_LIMIT = $batchLimit
    Write-Host "[OK] LANGSMITH_BATCH_INGEST_SIZE_LIMIT: $batchLimit" -ForegroundColor Green
}

Write-Host ""
Write-Host "LangSmith tracing env vars set:" -ForegroundColor Cyan
Write-Host "  LANGSMITH_TRACING_V2 = true"
Write-Host "  LANGSMITH_API_KEY    = $($env:LANGSMITH_API_KEY.Substring(0, 20))..."
Write-Host "  LANGSMITH_ENDPOINT   = $env:LANGSMITH_ENDPOINT"
Write-Host "  LANGSMITH_PROJECT    = $env:LANGSMITH_PROJECT"
Write-Host ""

# -- 4. Check mode only --
if ($Check) {
    Write-Host "Checking langgraph dev server status..." -ForegroundColor Cyan
    try {
        $resp = Invoke-RestMethod -Uri "http://127.0.0.1:2024/info" -TimeoutSec 3
        $langsmithEnabled = $resp.flags.langsmith
        if ($langsmithEnabled) {
            Write-Host "[OK] LangSmith tracing: ENABLED" -ForegroundColor Green
        } else {
            Write-Host "[FAIL] LangSmith tracing: DISABLED" -ForegroundColor Red
            Write-Host "  Restart langgraph dev with this script" -ForegroundColor Yellow
        }
        Write-Host "  flags: $($resp.flags | ConvertTo-Json -Compress)"
    } catch {
        Write-Host "[FAIL] langgraph dev server not running" -ForegroundColor Red
    }
    return
}

# -- 5. Clean old checkpoint data (optional) --
$checkpointDir = Join-Path $PSScriptRoot ".langgraph_api"
if (Test-Path $checkpointDir) {
    Write-Host "[INFO] Found .langgraph_api/ (previous checkpoint)" -ForegroundColor Cyan
    $answer = Read-Host "  Delete it? (y/n, default n)"
    if ($answer -eq 'y') {
        Remove-Item $checkpointDir -Recurse -Force
        Write-Host "[OK] .langgraph_api/ deleted" -ForegroundColor Green
    }
}

# -- 6. Start langgraph dev --
Write-Host ""
Write-Host "Starting langgraph dev..." -ForegroundColor Cyan
Write-Host ("=" * 50)

if ($NoReload) {
    langgraph dev --no-reload
} else {
    langgraph dev
}
