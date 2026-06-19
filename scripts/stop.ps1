# stop.ps1 — Stop Permit RAG Application
# Shuts down Postgres/Neo4j containers and stops running dev servers.

Write-Host "Stopping Docker containers..." -ForegroundColor Cyan
& docker compose down

Write-Host "Stopping FastAPI backend and Vite frontend processes..." -ForegroundColor Cyan
# Safely stop any orphaned uvicorn or node/vite processes on this machine
Get-Process | Where-Object { $_.ProcessName -eq "uvicorn" -or $_.CommandLine -like "*uvicorn*" } | Stop-Process -Force -ErrorAction SilentlyContinue
Get-Process | Where-Object { $_.ProcessName -eq "node" -and $_.CommandLine -like "*vite*" } | Stop-Process -Force -ErrorAction SilentlyContinue

Write-Host "All services stopped." -ForegroundColor Green
