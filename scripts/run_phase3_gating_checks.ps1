# Phase 3 Gating Checks Script (PowerShell)
# -----------------------------------------------------------------------------
# Purpose:
#   Run environment and configuration checks required before Phase 3 (LLM Reasoning)
#   implementation. This validates:
#     - Embedding model name and dimension (env and code)
#     - Redis connectivity (CLI or Python fallback)
#     - Postgres pgvector extension presence (psql, with guidance if missing)
#     - Presence of OPENAI_API_KEY in .env
#
# How to run (exact steps to avoid terminal errors):
#   1) Open PowerShell
#   2) cd c:\Users\Usuario\Documents\Workspace\micro_pymes\backend
#   3) Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
#      (This enables running the script for the current PowerShell session only)
#   4) .\scripts\run_phase3_gating_checks.ps1
#
# Notes:
#   - This script automatically switches the current directory to the project root.
#   - If redis-cli or psql are not installed, the script provides guidance or Python fallbacks.
#   - No secrets are printed; only presence checks and summary results are shown.
# -----------------------------------------------------------------------------

Set-StrictMode -Version Latest
$ErrorActionPreference = "Continue"

function Write-Section {
    param([string]$Title)
    Write-Host ""
    Write-Host "========== $Title ==========" -ForegroundColor Cyan
}

function Write-Sub {
    param([string]$Text)
    Write-Host "  -> $Text" -ForegroundColor DarkCyan
}

function Write-Result {
    param([string]$Key, [string]$Value)
    Write-Host ("  - {0}: {1}" -f $Key, $Value) -ForegroundColor Green
}

# Move to project root (this script lives in scripts/)
try {
    $root = Join-Path $PSScriptRoot ".."
    Set-Location $root
} catch {
    Write-Host "Failed to change directory to project root: $($_.Exception.Message)" -ForegroundColor Red
}

Write-Section "Environment Overview"
Write-Result "Current Directory" (Get-Location).Path
Write-Result "PowerShell Version" $PSVersionTable.PSVersion.ToString()

# -----------------------------------------------------------------------------
# 1) Embedding env variables (EMBEDDING_MODEL_NAME, EMBEDDING_DIM)
# -----------------------------------------------------------------------------
Write-Section "Embedding Environment Variables"
$envModel = $Env:EMBEDDING_MODEL_NAME
$envDim   = $Env:EMBEDDING_DIM

if ([string]::IsNullOrWhiteSpace($envModel)) {
    Write-Sub "EMBEDDING_MODEL_NAME not set in environment. Will try reading from .env"
    if (Test-Path ".\.env") {
        $modelLine = Select-String -Path ".\.env" -Pattern "^\s*EMBEDDING_MODEL_NAME\s*=" -SimpleMatch -ErrorAction SilentlyContinue
        if ($modelLine) {
            $parts = $modelLine.Line.Split("=",2)
            if ($parts.Count -ge 2) { $envModel = $parts[1].Trim() }
        }
    }
}
if ([string]::IsNullOrWhiteSpace($envDim)) {
    Write-Sub "EMBEDDING_DIM not set in environment. Will try reading from .env"
    if (Test-Path ".\.env") {
        $dimLine = Select-String -Path ".\.env" -Pattern "^\s*EMBEDDING_DIM\s*=" -SimpleMatch -ErrorAction SilentlyContinue
        if ($dimLine) {
            $parts = $dimLine.Line.Split("=",2)
            if ($parts.Count -ge 2) { $envDim = $parts[1].Trim() }
        }
    }
}

Write-Result "EMBEDDING_MODEL_NAME (env/.env)" ($(if ([string]::IsNullOrWhiteSpace($envModel)) { "<not set>" } else { $envModel }))
Write-Result "EMBEDDING_DIM (env/.env)" ($(if ([string]::IsNullOrWhiteSpace($envDim)) { "<not set>" } else { $envDim }))

# -----------------------------------------------------------------------------
# 2) Python checks from code
# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------
# 1b) Embedding model default from source (no Python import)
# -----------------------------------------------------------------------------
Write-Section "Embedding Model (source parse)"
try {
    $epPath = "app\services\ml\embedding_pipeline.py"
    if (Test-Path $epPath) {
        $content = Get-Content $epPath -Raw
        # Match: model_name: str = "sentence-transformers/all-MiniLM-L6-v2"
        $match = [regex]::Match($content, 'model_name\s*:\s*str\s*=\s*"([^"]+)"')
        if ($match.Success) {
            Write-Result "embedding_pipeline default model_name" $match.Groups[1].Value
        } else {
            Write-Sub "Could not parse default model_name from embedding_pipeline.py"
        }
    } else {
        Write-Sub "embedding_pipeline.py not found at $epPath"
    }
} catch {
    Write-Host "Source parse error: $($_.Exception.Message)" -ForegroundColor Yellow
}
Write-Section "Python Checks (from project code)"
# 2a) Print EmbeddingConfig.model_name (what embedding pipeline uses)
try {
    $pyCode1 = 'from app.services.ml.embedding_pipeline import EmbeddingConfig; print(EmbeddingConfig().model_name)'
    $out1 = & python -c $pyCode1 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Result "EmbeddingConfig().model_name" (([string]$out1).Trim())
    } else {
        Write-Host "Python error for EmbeddingConfig().model_name: $out1" -ForegroundColor Yellow
    }
} catch {
    Write-Host "Python not available or import failed: $($_.Exception.Message)" -ForegroundColor Red
}

# 2b) Print settings.EMBEDDING_MODEL_NAME and settings.EMBEDDING_DIM (from app/core/config.py)
try {
    $pyCode2 = 'from app.core.config import settings; print(settings.EMBEDDING_MODEL_NAME, settings.EMBEDDING_DIM)'
    $out2 = & python -c $pyCode2 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Result "settings.EMBEDDING_MODEL_NAME & settings.EMBEDDING_DIM" (([string]$out2).Trim())
    } else {
        Write-Host "Python error for settings.*: $out2" -ForegroundColor Yellow
    }
} catch {
    Write-Host "Python not available or import failed: $($_.Exception.Message)" -ForegroundColor Red
}

# -----------------------------------------------------------------------------
# 3) Redis connectivity
# -----------------------------------------------------------------------------
Write-Section "Redis Connectivity"
$redisCli = Get-Command redis-cli -ErrorAction SilentlyContinue
if ($redisCli) {
    try {
        $redisPing = & redis-cli PING 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Result "redis-cli PING" ($redisPing.Trim())
        } else {
            Write-Host "redis-cli PING error: $redisPing" -ForegroundColor Yellow
        }
    } catch {
        Write-Host "redis-cli execution failed: $($_.Exception.Message)" -ForegroundColor Yellow
    }
} else {
    Write-Sub "redis-cli not found. Trying TCP connectivity test (no Python dependency)..."
    try {
        $redisUrl = $Env:REDIS_URL
        if ([string]::IsNullOrWhiteSpace($redisUrl)) { $redisUrl = "redis://localhost:6379/0" }
        $uri = [System.Uri]$redisUrl
        $host = $uri.Host
        $port = if ($uri.Port -gt 0) { $uri.Port } else { 6379 }
        $client = New-Object System.Net.Sockets.TcpClient
        $async = $client.BeginConnect($host, $port, $null, $null)
        $connected = $async.AsyncWaitHandle.WaitOne(3000) -and $client.Connected
        if ($connected) {
            Write-Result "Redis (TCP)" ("TCP CONNECT OK to {0}:{1}" -f $host, $port)
        } else {
            Write-Host ("Redis TCP connect failed (timeout) to {0}:{1}" -f $host, $port) -ForegroundColor Yellow
        }
        $client.Close()
    } catch {
        Write-Host "Redis TCP check error: $($_.Exception.Message)" -ForegroundColor Yellow
    }
}

# -----------------------------------------------------------------------------
# 4) Postgres pgvector extension presence
# -----------------------------------------------------------------------------
Write-Section "Postgres pgvector Extension"
# Detect if we are likely using SQLite (no DB_PASSWORD set) and skip pgvector check
$envDbPwd = $Env:DB_PASSWORD
if ([string]::IsNullOrWhiteSpace($envDbPwd) -and (Test-Path ".\.env")) {
    try {
        $pwdLine = Select-String -Path ".\.env" -Pattern "^\s*DB_PASSWORD\s*=" -SimpleMatch -ErrorAction SilentlyContinue
        if ($pwdLine) {
            $parts = $pwdLine.Line.Split("=",2)
            if ($parts.Count -ge 2) { $envDbPwd = $parts[1].Trim() }
        }
    } catch {
        # ignore parse errors
    }
}
if ([string]::IsNullOrWhiteSpace($envDbPwd)) {
    Write-Sub "No DB_PASSWORD detected (likely using SQLite dev). Skipping pgvector check."
} else {
    $psql = Get-Command psql -ErrorAction SilentlyContinue
    if ($psql) {
        try {
            $query = 'SELECT extname, extversion FROM pg_extension WHERE extname = ''vector'';'
            $psqlOut = & psql -d micropymes -c $query 2>&1
            if ($LASTEXITCODE -eq 0) {
                Write-Host $psqlOut
            } else {
                Write-Host "psql query failed: $psqlOut" -ForegroundColor Yellow
            }
        } catch {
            Write-Host "psql execution failed: $($_.Exception.Message)" -ForegroundColor Yellow
        }
    } else {
        Write-Sub "psql not found. Please run this manually in a shell with psql available:"
        Write-Host '  psql -d micropymes -c "SELECT extname, extversion FROM pg_extension WHERE extname = ''vector'';"' -ForegroundColor Yellow
    }
}

# -----------------------------------------------------------------------------
# 5) OPENAI_API_KEY presence (.env)
# -----------------------------------------------------------------------------
Write-Section "OPENAI_API_KEY Presence in .env"
if (Test-Path ".\.env") {
    try {
        $line = Select-String -Path ".\.env" -Pattern "^\s*OPENAI_API_KEY\s*=" -SimpleMatch -ErrorAction SilentlyContinue
        if ($line) {
            $safe = $line.Line.Trim()
            # Do not print the actual key; only indicate presence
            Write-Result "OPENAI_API_KEY" "present in .env (value hidden)"
        } else {
            Write-Result "OPENAI_API_KEY" "not found in .env"
        }
    } catch {
        Write-Host "Failed to read .env: $($_.Exception.Message)" -ForegroundColor Yellow
    }
} else {
    Write-Sub ".env file not found in project root."
}

# -----------------------------------------------------------------------------
# 6) Summary and next steps
# -----------------------------------------------------------------------------
Write-Section "Summary & Next Steps"
Write-Host "Review the outputs above and paste them back into the chat." -ForegroundColor Cyan
Write-Host "I will validate EMBEDDING_DIM vs model selection, Redis connectivity, and pgvector presence and then proceed." -ForegroundColor Cyan