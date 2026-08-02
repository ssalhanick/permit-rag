# scripts/reprocess_corpus.ps1 — full corpus reprocess + RAGAs report (PowerShell)
# ============================================================================
# Re-chunks every existing document (picking up any chunking-strategy change
# in ingestion/chunker.py -- e.g. static context prefix and structure-aware
# splitting), force re-embeds the result, then runs the RAGAs eval gate.
#
# Usage:
#   .\scripts\reprocess_corpus.ps1 -Local
#   .\scripts\reprocess_corpus.ps1 -DatabaseUrl "postgresql://..."
# ============================================================================

[CmdletBinding()]
param(
    [switch]$Local,
    [string]$DatabaseUrl
)

# Set ErrorActionPreference to Continue so stderr output from Python logging doesn't trip terminating exceptions
$ErrorActionPreference = "Continue"

if (-not (Test-Path "pyproject.toml")) {
    Write-Error "Run this script from the repo root (pyproject.toml not found in $(Get-Location))."
    exit 2
}

if (-not $Local -and [string]::IsNullOrWhiteSpace($DatabaseUrl)) {
    Write-Host "Usage:" -ForegroundColor Yellow
    Write-Host "  .\scripts\reprocess_corpus.ps1 -Local"
    Write-Host "  .\scripts\reprocess_corpus.ps1 -DatabaseUrl 'postgresql://...'"
    Write-Host "`nA DB target parameter (-Local or -DatabaseUrl) is required." -ForegroundColor Red
    exit 2
}

$dbArgs = @()
if ($Local) {
    $dbArgs += "--local"
} else {
    $dbArgs += "--database-url"
    $dbArgs += $DatabaseUrl
}

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$reportDir = "evaluation/results/reprocess/$timestamp"
if (-not (Test-Path $reportDir)) {
    New-Item -ItemType Directory -Path $reportDir -Force | Out-Null
}

$logFile = "$reportDir/reprocess_$timestamp.log"
$reportFile = "$reportDir/reprocess_${timestamp}_report.txt"

function Write-Log {
    param([string]$Message)
    $logMsg = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $Message"
    Write-Host $logMsg
    Add-Content -Path $logFile -Value $logMsg
}

$step1Status = "SKIPPED"
$step2Status = "SKIPPED"
$step3Status = "SKIPPED"

function Write-Report {
    $reportLines = @(
        "Corpus reprocess report -- $timestamp",
        "DB target args: $($dbArgs -join ' ')",
        "",
        "Step 1 (re-chunk, scripts.ingest_documents --include-existing): $step1Status",
        "Step 2 (force re-embed, ingestion.embedder --force):            $step2Status",
        "Step 3 (RAGAs eval, --no-answer-cache --export):                $step3Status",
        ""
    )

    if (Test-Path $logFile) {
        $reportLines += "-- RAGAs summary (grepped from full log) --"
        $avgMatches = Select-String -Path $logFile -Pattern "^\s*AVG" -Context 0,2
        if ($avgMatches) {
            foreach ($m in $avgMatches) {
                $reportLines += $m.Line
                foreach ($ctx in $m.Context.PostContext) {
                    $reportLines += $ctx
                }
            }
        } else {
            $reportLines += "(no RAGAs summary captured in this run -- see full log)"
        }
        $reportLines += ""
        $reportLines += "Full log: $logFile"
    }

    $reportContent = $reportLines -join "`n"
    Set-Content -Path $reportFile -Value $reportContent
    Write-Host $reportContent
}

Write-Log "=== Corpus reprocess starting ==="
Write-Log "DB target args: $($dbArgs -join ' ')"
if ($env:ENVIRONMENT) {
    Write-Log "Environment: $env:ENVIRONMENT"
}

# Step 1: Re-chunk
Write-Log "--- Step 1: re-chunk (scripts.ingest_documents --include-existing) ---"
py -m scripts.ingest_documents --include-existing @dbArgs 2>&1 | Tee-Object -FilePath $logFile -Append
if ($LASTEXITCODE -eq 0) {
    $step1Status = "OK"
    Write-Log "Step 1 OK"
} else {
    $step1Status = "FAILED (exit $LASTEXITCODE)"
    Write-Log "Step 1 FAILED (exit $LASTEXITCODE) -- see $logFile."
    Write-Log "Stopping before re-embed: re-embedding stale chunking data would waste the run."
    Write-Report
    exit 1
}

# Step 2: Force re-embed
Write-Log "--- Step 2: force re-embed (ingestion.embedder --force) ---"
py -m ingestion.embedder --force @dbArgs 2>&1 | Tee-Object -FilePath $logFile -Append
if ($LASTEXITCODE -eq 0) {
    $step2Status = "OK"
    Write-Log "Step 2 OK"
} else {
    $step2Status = "FAILED (exit $LASTEXITCODE)"
    Write-Log "Step 2 FAILED (exit $LASTEXITCODE) -- see $logFile."
    Write-Log "Stopping before RAGAs: scoring against stale embeddings would be a misleading comparison."
    Write-Report
    exit 1
}

# Step 3: RAGAs eval
Write-Log "--- Step 3: RAGAs eval (--no-answer-cache --export) ---"
py -m evaluation.ragas_eval --no-answer-cache --export @dbArgs 2>&1 | Tee-Object -FilePath $logFile -Append
if ($LASTEXITCODE -eq 0) {
    $step3Status = "OK"
    Write-Log "Step 3 OK"
} else {
    $step3Status = "FAILED (exit $LASTEXITCODE)"
    Write-Log "Step 3 FAILED (exit $LASTEXITCODE) -- see $logFile."
}

Write-Report

if ($step3Status -ne "OK") {
    Write-Log "=== Corpus reprocess finished with failures ==="
    exit 1
}

Write-Log "=== Corpus reprocess complete -- all steps OK ==="
Write-Log "Report: $reportFile"
exit 0
