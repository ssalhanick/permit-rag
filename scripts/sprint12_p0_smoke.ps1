# Sprint 12 P0 prod smoke probes (read-only). Requires network.
$Base = "https://permits.scottsalhanick.com"
$Failed = 0

function Assert-Ok($Name, $Cond) {
    if ($Cond) { Write-Host "[PASS] $Name" -ForegroundColor Green }
    else { Write-Host "[FAIL] $Name" -ForegroundColor Red; $script:Failed++ }
}

try {
    $health = Invoke-RestMethod -Uri "$Base/health" -Method Get -TimeoutSec 30
    Assert-Ok "GET /health" ($health.status -in @("ok", "healthy") -or $health.ok -eq $true)
} catch {
    Assert-Ok "GET /health" $false
}

try {
    $docs = Invoke-WebRequest -Uri "$Base/api/documents" -Method Get -TimeoutSec 30 -UseBasicParsing
    $body = $docs.Content
    Assert-Ok "GET /api/documents not HTML" (-not ($body.Trim().StartsWith("<!")))
    Assert-Ok "GET /api/documents non-empty" ($body -ne "[]")
} catch {
    Assert-Ok "GET /api/documents" $false
}

try {
    $spa = Invoke-WebRequest -Uri "$Base/projects" -Method Get -TimeoutSec 30 -UseBasicParsing
    Assert-Ok "GET /projects returns HTML SPA" ($spa.Content -match "<!DOCTYPE|<html")
} catch {
    Assert-Ok "GET /projects SPA" $false
}

if ($Failed -gt 0) { exit 1 }
Write-Host "All Sprint 12 P0 smoke probes passed." -ForegroundColor Green
