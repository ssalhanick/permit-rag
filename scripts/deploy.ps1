# scripts/deploy.ps1 — Local-to-Cloud Deployer for Permit RAG
# Automates deploying infrastructure, backend containers, and frontend static assets.

param (
    [switch]$InfraOnly,
    [switch]$BackendOnly,
    [switch]$FrontendOnly
)

$ErrorActionPreference = "Stop"

# Disable the AWS CLI interactive pager to prevent scripts from pausing on large JSON outputs
$env:AWS_PAGER = ""

# Default to running all steps if no switch is specified
$runAll = -not ($InfraOnly -or $BackendOnly -or $FrontendOnly)

# Helper function to get Terraform outputs
function Get-TerraformOutput {
    param([string]$name)
    try {
        $val = & terraform -chdir=terraform output -raw $name 2>$null
        if ($LastExitCode -eq 0 -and $val -and -not ($val.Contains("No outputs found"))) {
            return $val.Trim()
        }
    } catch {
        # Silent fail
    }
    return $null
}

# --- 1. Infrastructure Deployment (Terraform) ---
if ($runAll -or $InfraOnly) {
    Write-Host "`n=== [1/3] Deploying Infrastructure with Terraform ===" -ForegroundColor Cyan
    if (-not (Test-Path "terraform")) {
        Write-Error "Could not find 'terraform' directory in the project root."
        exit 1
    }
    
    Write-Host "Running terraform init & apply..." -ForegroundColor Yellow
    & terraform -chdir=terraform init
    & terraform -chdir=terraform apply -auto-approve
    
    if ($LastExitCode -ne 0) {
        Write-Error "Terraform deployment failed."
        exit 1
    }
    Write-Host "Infrastructure deployment succeeded!" -ForegroundColor Green
}

# Ensure we can retrieve AWS resource details from Terraform output before deploying app layers
$ecrRepoUri = Get-TerraformOutput "ecr_repository_url"
$s3BucketName = Get-TerraformOutput "frontend_bucket_name"
$cloudfrontId = Get-TerraformOutput "cloudfront_distribution_id"
$awsRegion = Get-TerraformOutput "aws_region"

if (-not $awsRegion) { $awsRegion = "us-east-1" }

if (-not ($InfraOnly) -and (-not $ecrRepoUri -or -not $s3BucketName)) {
    Write-Error "Could not retrieve production resource names from Terraform output. Please run 'npm run deploy:infra' first."
    exit 1
}

# --- 2. Backend Deployment (Docker + ECR + ECS) ---
if ($runAll -or $BackendOnly) {
    Write-Host "`n=== [2/3] Deploying Backend Container (ECS Fargate) ===" -ForegroundColor Cyan
    Write-Host "Target ECR: $ecrRepoUri" -ForegroundColor Yellow
    
    # Extract Registry URL (everything before the /repository-name)
    $ecrRegistry = $ecrRepoUri.Split('/')[0]
    
    # 2.1 Authenticate Docker with AWS ECR
    Write-Host "Authenticating Docker with AWS ECR..." -ForegroundColor Yellow
    cmd.exe /c "aws ecr get-login-password --region $awsRegion | docker login --username AWS --password-stdin $ecrRegistry"
    if ($LastExitCode -ne 0) {
        Write-Error "ECR login failed. Ensure AWS CLI is configured."
        exit 1
    }
    
    # 2.2 Build Docker Image
    Write-Host "Building Docker image..." -ForegroundColor Yellow
    & docker build -t permit-rag-backend .
    if ($LastExitCode -ne 0) {
        Write-Error "Docker build failed."
        exit 1
    }
    
    # 2.3 Tag & Push
    Write-Host "Tagging and pushing image to ECR..." -ForegroundColor Yellow
    & docker tag permit-rag-backend:latest "${ecrRepoUri}:latest"
    & docker push "${ecrRepoUri}:latest"
    if ($LastExitCode -ne 0) {
        Write-Error "ECR push failed."
        exit 1
    }
    
    # 2.4 Force ECS Redeployment
    Write-Host "Rolling new backend container deployment in ECS..." -ForegroundColor Yellow
    & aws ecs update-service --cluster permit-rag-cluster --service permit-rag-service --force-new-deployment --region $awsRegion
    if ($LastExitCode -ne 0) {
        Write-Error "ECS service update failed."
        exit 1
    }
    
    Write-Host "Backend deployment initiated successfully!" -ForegroundColor Green
}

# --- 3. Frontend Deployment (Build + S3 + CloudFront) ---
if ($runAll -or $FrontendOnly) {
    Write-Host "`n=== [3/3] Deploying Frontend (S3 + CloudFront) ===" -ForegroundColor Cyan
    Write-Host "Target S3 Bucket: s3://$s3BucketName" -ForegroundColor Yellow
    
    # 3.1 Build assets
    Write-Host "Building React frontend production assets..." -ForegroundColor Yellow
    Push-Location frontend
    try {
        & npm run build
    } finally {
        Pop-Location
    }
    if ($LastExitCode -ne 0) {
        Write-Error "Frontend build failed."
        exit 1
    }
    
    # 3.2 Upload to S3
    Write-Host "Syncing assets to S3 bucket..." -ForegroundColor Yellow
    & aws s3 sync frontend/dist/ "s3://$s3BucketName" --delete
    if ($LastExitCode -ne 0) {
        Write-Error "S3 sync failed."
        exit 1
    }
    
    # 3.3 CloudFront Cache Invalidation
    if ($cloudfrontId) {
        Write-Host "Invalidating CloudFront CDN cache (Distribution: $cloudfrontId)..." -ForegroundColor Yellow
        & aws cloudfront create-invalidation --distribution-id $cloudfrontId --paths "/*" --region $awsRegion
        if ($LastExitCode -ne 0) {
            Write-Warning "CloudFront invalidation command failed or skipped."
        }
    } else {
        Write-Warning "CloudFront Distribution ID not found in Terraform outputs. Skipping invalidation."
    }
    
    Write-Host "Frontend deployment completed successfully!" -ForegroundColor Green
}

Write-Host "`n==================================================" -ForegroundColor Green
Write-Host "Deployment scripts completed!" -ForegroundColor Green
Write-Host "==================================================" -ForegroundColor Green
