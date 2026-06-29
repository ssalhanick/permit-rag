# scripts/shutdown-prod.ps1 — Scale production stack down to save cost (Option A)
# Sets ECS desired count to 0 and stops RDS.

param(
    [string]$Region = "us-east-1",
    [string]$Cluster = "permit-rag-cluster",
    [string]$Service = "permit-rag-service",
    [string]$DbInstanceId = "permit-rag-postgres",
    [switch]$SkipRds,
    [switch]$KeepRdsRunning
)

$ErrorActionPreference = "Stop"
$env:AWS_PAGER = ""

function Invoke-Aws {
    param([string[]]$Args)
    & aws @Args
    if ($LastExitCode -ne 0) {
        throw "AWS CLI failed: aws $($Args -join ' ')"
    }
}

Write-Host "`n=== Shutdown production stack (save cost) ===" -ForegroundColor Cyan

Write-Host "`n[1/2] Scaling ECS service to 0 tasks..." -ForegroundColor Cyan
Invoke-Aws @(
    "ecs", "update-service",
    "--cluster", $Cluster,
    "--service", $Service,
    "--desired-count", "0",
    "--region", $Region
) | Out-Null
Write-Host "ECS scaled to 0. Fargate compute charges stop." -ForegroundColor Green
Write-Host "Note: ALB still bills ~`$18/mo while it exists." -ForegroundColor DarkGray

if (-not $SkipRds -and -not $KeepRdsRunning) {
    Write-Host "`n[2/2] Stopping RDS ($DbInstanceId)..." -ForegroundColor Cyan
    $status = (Invoke-Aws @(
        "rds", "describe-db-instances",
        "--db-instance-identifier", $DbInstanceId,
        "--region", $Region,
        "--query", "DBInstances[0].DBInstanceStatus",
        "--output", "text"
    )).Trim()

    if ($status -eq "stopped") {
        Write-Host "RDS already stopped." -ForegroundColor Green
    } elseif ($status -eq "stopping") {
        Write-Host "RDS is already stopping." -ForegroundColor Yellow
    } else {
        Invoke-Aws @("rds", "stop-db-instance", "--db-instance-identifier", $DbInstanceId, "--region", $Region) | Out-Null
        Write-Host "RDS stop requested." -ForegroundColor Green
        Write-Host "RDS auto-restarts after 7 days if left stopped." -ForegroundColor DarkGray
    }
} else {
    Write-Host "`n[2/2] RDS left running." -ForegroundColor DarkGray
}

Write-Host "`nStack scaled down." -ForegroundColor Green
Write-Host "Boot for next demo: npm run boot:prod" -ForegroundColor DarkGray
