# dev.ps1 — Permit RAG Dev Orchestrator
# Automates starting Docker, FastAPI backend, and Vite frontend on Windows.

$ErrorActionPreference = "Stop"

function Test-Docker {
    $oldPreference = $ErrorActionPreference
    $ErrorActionPreference = "SilentlyContinue"
    try {
        & docker ps >$null 2>&1
        return ($LastExitCode -eq 0)
    } catch {
        return $false
    } finally {
        $ErrorActionPreference = $oldPreference
    }
}

# 1. Verify/Start Docker
Write-Host "Checking Docker status..." -ForegroundColor Cyan
if (-not (Test-Docker)) {
    Write-Host "Docker daemon is not running. Launching Docker Desktop..." -ForegroundColor Yellow
    
    $dockerPaths = @(
        "C:\Program Files\Docker\Docker\Docker Desktop.exe",
        "${env:ProgramFiles}\Docker\Docker\Docker Desktop.exe",
        "${env:ProgramFiles(x86)}\Docker\Docker\Docker Desktop.exe"
    )
    $launched = $false
    foreach ($path in $dockerPaths) {
        if (Test-Path $path) {
            Start-Process $path
            $launched = $true
            break
        }
    }
    
    if (-not $launched) {
        Write-Host "WARNING: Could not locate Docker Desktop executable automatically." -ForegroundColor Red
        Write-Host "Please start Docker Desktop manually, then press any key to continue..." -ForegroundColor Yellow
        $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
    } else {
        Write-Host "Waiting for Docker daemon to become responsive..." -ForegroundColor Yellow
        while ($true) {
            Start-Sleep -Seconds 3
            if (Test-Docker) { break }
            Write-Host "." -NoNewline
        }
        Write-Host ""
    }
}

# 2. Spin up Docker containers
Write-Host "Starting Postgres (5433) and Neo4j (7687) containers..." -ForegroundColor Cyan
& docker compose up -d

# 3. Wait for PostgreSQL
Write-Host "Verifying database connection..." -ForegroundColor Cyan
$dbCheck = "FAIL"
try {
    $dbCheck = & .venv\Scripts\python -c "
import os, sys
from dotenv import load_dotenv
load_dotenv()
sys.path.append('.')
from db.client import ping
if ping():
    print('OK')
    sys.exit(0)
else:
    sys.exit(1)
"
} catch {
    # Ignore initial failure
}

if ($dbCheck.Trim() -ne "OK") {
    Write-Host "Database is warming up, waiting 5 seconds..." -ForegroundColor Yellow
    Start-Sleep -Seconds 5
}

# 4. Start Backend (New Window)
Write-Host "Launching FastAPI backend in separate window (port 8000)..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", "`$Host.UI.RawUI.WindowTitle = 'permit_rag Backend'; Write-Host 'FastAPI Backend running...'; .venv\Scripts\python -m uvicorn api.main:app --port 8000 --reload"

# 5. Start Frontend (New Window)
Write-Host "Launching Vite frontend in separate window (port 5173)..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", "`$Host.UI.RawUI.WindowTitle = 'permit_rag Frontend'; Write-Host 'Vite Frontend running...'; cd frontend; npm run dev"

Write-Host "`n==================================================" -ForegroundColor Green
Write-Host "Application is starting up!" -ForegroundColor Green
Write-Host "  - Frontend   : http://localhost:5173" -ForegroundColor Green
Write-Host "  - Backend API: http://localhost:8000/docs" -ForegroundColor Green
Write-Host "==================================================" -ForegroundColor Green
Write-Host "Closing the backend or frontend windows will stop those services." -ForegroundColor Yellow
Write-Host "Run 'docker compose down' to stop the database containers when finished." -ForegroundColor Yellow
