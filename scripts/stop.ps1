# stop.ps1 — Stop Permit RAG Application
# Shuts down Postgres/Neo4j containers and stops running dev servers.

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

Write-Host "Stopping Docker containers..." -ForegroundColor Cyan
if (Test-Docker) {
    & docker compose down
} else {
    Write-Host "Docker daemon is not running. Skipping container shutdown." -ForegroundColor Yellow
}

Write-Host "Stopping FastAPI backend and Vite frontend processes..." -ForegroundColor Cyan
# Safely stop any orphaned uvicorn or node/vite processes on this machine
Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -eq "uvicorn" -or $_.CommandLine -like "*uvicorn*" } | Stop-Process -Force -ErrorAction SilentlyContinue
Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -eq "node" -and $_.CommandLine -like "*vite*" } | Stop-Process -Force -ErrorAction SilentlyContinue

Write-Host "All services stopped." -ForegroundColor Green
