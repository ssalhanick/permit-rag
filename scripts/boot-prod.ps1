# scripts/boot-prod.ps1 — Start production stack for demos (Option A)
# Starts RDS (if stopped), scales ECS to 1 task, waits for health.

param(
    [string]$Region = "us-east-1",
    [string]$Cluster = "permit-rag-cluster",
    [string]$Service = "permit-rag-service",
    [string]$DbInstanceId = "permit-rag-postgres",
    [string]$HealthUrl = "https://permits.scottsalhanick.com/health",
    [int]$HealthRetries = 12,
    [int]$HealthRetrySeconds = 15,
    [switch]$SkipRds,
    [switch]$SkipHealthCheck
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

function Get-RdsStatus {
    $status = Invoke-Aws @(
        "rds", "describe-db-instances",
        "--db-instance-identifier", $DbInstanceId,
        "--region", $Region,
        "--query", "DBInstances[0].DBInstanceStatus",
        "--output", "text"
    )
    return $status.Trim()
}

Write-Host "`n=== Boot production stack (demo mode) ===" -ForegroundColor Cyan
Write-Host "Region: $Region" -ForegroundColor DarkGray

# --- 1. RDS ---
if (-not $SkipRds) {
    Write-Host "`n[1/3] Checking RDS ($DbInstanceId)..." -ForegroundColor Cyan
    $dbStatus = Get-RdsStatus
    Write-Host "Current RDS status: $dbStatus" -ForegroundColor Yellow

    switch ($dbStatus) {
        "available" {
            Write-Host "RDS already running." -ForegroundColor Green
        }
        "stopped" {
            Write-Host "Starting RDS (usually 5-10 minutes)..." -ForegroundColor Yellow
            Invoke-Aws @("rds", "start-db-instance", "--db-instance-identifier", $DbInstanceId, "--region", $Region) | Out-Null
            Write-Host "Waiting for RDS to become available..." -ForegroundColor Yellow
            Invoke-Aws @("rds", "wait", "db-instance-available", "--db-instance-identifier", $DbInstanceId, "--region", $Region)
            Write-Host "RDS is available." -ForegroundColor Green
        }
        "starting" {
            Write-Host "RDS is already starting — waiting..." -ForegroundColor Yellow
            Invoke-Aws @("rds", "wait", "db-instance-available", "--db-instance-identifier", $DbInstanceId, "--region", $Region)
            Write-Host "RDS is available." -ForegroundColor Green
        }
        default {
            Write-Host "RDS state '$dbStatus' — waiting for available..." -ForegroundColor Yellow
            Invoke-Aws @("rds", "wait", "db-instance-available", "--db-instance-identifier", $DbInstanceId, "--region", $Region)
            Write-Host "RDS is available." -ForegroundColor Green
        }
    }
} else {
    Write-Host "`n[1/3] Skipping RDS (--SkipRds)." -ForegroundColor DarkGray
}

# --- 2. ECS ---
Write-Host "`n[2/3] Scaling ECS service to 1 task..." -ForegroundColor Cyan
Invoke-Aws @(
    "ecs", "update-service",
    "--cluster", $Cluster,
    "--service", $Service,
    "--desired-count", "1",
    "--force-new-deployment",
    "--region", $Region
) | Out-Null

Write-Host "Waiting for ECS service to stabilize (ALB grace period is 120s)..." -ForegroundColor Yellow
Invoke-Aws @("ecs", "wait", "services-stable", "--cluster", $Cluster, "--services", $Service, "--region", $Region)
Write-Host "ECS service is stable." -ForegroundColor Green

# --- 3. Health check ---
if (-not $SkipHealthCheck) {
    Write-Host "`n[3/3] Checking $HealthUrl ..." -ForegroundColor Cyan
    $healthy = $false

    for ($i = 1; $i -le $HealthRetries; $i++) {
        try {
            $response = Invoke-WebRequest -Uri $HealthUrl -UseBasicParsing -TimeoutSec 30
            $body = $response.Content
            Write-Host "Attempt $i/$HealthRetries — HTTP $($response.StatusCode)" -ForegroundColor Yellow
            Write-Host $body

            if ($response.StatusCode -eq 200 -and $body -match '"database"\s*:\s*true') {
                $healthy = $true
                break
            }
            if ($response.StatusCode -eq 200 -and $body -match '"status"\s*:\s*"healthy"') {
                $healthy = $true
                break
            }
        } catch {
            Write-Host "Attempt $i/$HealthRetries — $($_.Exception.Message)" -ForegroundColor Yellow
        }

        if ($i -lt $HealthRetries) {
            Start-Sleep -Seconds $HealthRetrySeconds
        }
    }

    if (-not $healthy) {
        Write-Host "`nHealth check did not pass yet." -ForegroundColor Red
        Write-Host "Tail logs: aws logs tail /ecs/permit-rag-backend --follow --region $Region" -ForegroundColor Yellow
        exit 1
    }

    Write-Host "`nProduction stack is up and healthy." -ForegroundColor Green
} else {
    Write-Host "`n[3/3] Skipping health check (--SkipHealthCheck)." -ForegroundColor DarkGray
    Write-Host "Production ECS task started." -ForegroundColor Green
}

Write-Host "`nSite: https://permits.scottsalhanick.com" -ForegroundColor Green
Write-Host "Shutdown after demo: npm run shutdown:prod" -ForegroundColor DarkGray
