# Step-by-Step AWS Cloud Deployment Guide

This guide outlines the practical, step-by-step tasks required to deploy the `permit_rag` application stack to AWS.

---

## Phase 1: Prerequisites & Cloud Provider Setup

### Step 1.1: AWS Account & CLI Configure
1. Create or log into your [AWS Console](https://aws.amazon.com/).
2. **Retrieve your AWS Access Keys**:
   *   In the top search bar of the AWS Console, search for **IAM** (Identity and Access Management).
   *   Click **Users** in the left sidebar and select your user profile.
   *   Go to the **Security credentials** tab.
   *   Scroll down to the **Access keys** section and click **Create access key**.
   *   Select **Command Line Interface (CLI)** as the use case, check the box to confirm, and click **Next**.
   *   Click **Create access key**. Copy the **Access Key ID** and **Secret Access Key** (download the `.csv` file as the secret key cannot be retrieved again).
3. Install the [AWS CLI](https://aws.amazon.com/cli/).
4. Open a terminal (you can run this inside the `permit_rag` directory or any directory on your computer, as configuration keys are stored globally in your home directory `~/.aws/`):
   ```bash
   aws configure
   ```
   *Provide your Access Key ID, Secret Access Key, preferred region (e.g., `us-east-1`), and default output format (`json`).*


### Step 1.2: Install Terraform
1. Download and install the [Terraform CLI](https://developer.hashicorp.com/terraform/downloads).
2. Verify the installation:
   ```bash
   terraform -v
   ```

### Step 1.3: Provision Neo4j AuraDB (Managed Graph Layer)
1. Go to [Neo4j Aura Console](https://console.neo4j.io/) and register a free account.
2. Click **Create Instance** -> Choose **AuraDB Free**.
3. Download the generated credentials file containing your database password and Connection URI (starts with `neo4j+s://`).

---

## Phase 2: Secure Secret Management

Before spinning up any computing servers, store secret keys securely in AWS Systems Manager (SSM) Parameter Store so they are not hardcoded.

1. Go to AWS Console -> **Systems Manager** -> **Parameter Store**.
2. Store the following values as **SecureString** parameters:
   *   `/permit_rag/prod/anthropic_api_key` (Your Claude API key)
   *   `/permit_rag/prod/jwt_secret` (A randomly generated 32-character string)
   *   `/permit_rag/prod/admin_token` (A secure administrative access token)
   *   `/permit_rag/prod/neo4j_bolt_url` (Your AuraDB connection URI)
   *   `/permit_rag/prod/neo4j_auth` (Format: `neo4j/<your-auradb-password>`)

---

## Phase 3: Infrastructure Provisioning via Terraform

Create a `terraform/` directory in the root of the project to hold the infrastructure configurations.

### Step 3.1: Initialize and Run Terraform
1. Change directory into your terraform configuration folder.
2. Initialize Terraform to download the AWS provider plugins:
   ```bash
   terraform init
   ```
3. Preview the infrastructure plan:
   ```bash
   terraform plan
   ```
4. Deploy the infrastructure to AWS:
   ```bash
   terraform apply
   ```
   *This will deploy the VPC, private/public subnets, security groups, RDS PostgreSQL database, Application Load Balancer (ALB), ECS Fargate service, and S3/CloudFront frontend hosting.*

---

## Automated Deployments via NPM Scripts

To simplify deployments, root-level `npm run` scripts are available to automate Terraform provisioning, Docker container builds/pushes, and frontend S3 syncing.

### Full Pipeline Deploy
To deploy the infrastructure, backend container, and frontend assets sequentially in one command:
```powershell
npm run deploy
```

### Targeted Deployments
If you only need to update a specific tier of the application, run these targeted commands:
*   **Infrastructure Only**: `npm run deploy:infra`
*   **Backend Code Only**: `npm run deploy:backend`
*   **Frontend Code Only**: `npm run deploy:frontend`

*Note: The deploy script dynamically reads resource names (like the ECR registry and S3 bucket name) from your local Terraform state output so you do not need to manually copy resource names into the scripts.*

---


## Phase 4: Database Initialization (PostgreSQL)

Once Amazon RDS is provisioned, you must apply the SQL schemas.

### Step 4.1: Retrieve the Database Connection String
1. Look at the outputs printed by `terraform apply` or retrieve the database endpoint from the RDS Console.
2. Construct your production database URL:
   ```
   postgresql://postgres:<your_db_password>@<rds_endpoint_address>:5432/permit_rag
   ```

### Step 4.2: Run Schemas and Seed Data
1. Temporarily allow your IP in the RDS Security Group, or use an EC2 bastion host / VPN.
2. Run the SQL schema script against the RDS instance:
   ```bash
   psql -h <rds_endpoint_address> -U postgres -d permit_rag -f db/schema.sql
   ```
3. Initialize the roles and seed data:
   ```bash
   psql -h <rds_endpoint_address> -U postgres -d permit_rag -f db/init/01_extensions.sql
   psql -h <rds_endpoint_address> -U postgres -d permit_rag -f db/init/02_roles.sql
   ```

---

## Phase 5: Containerizing and Deploying the FastAPI Backend

### Step 5.1: Create a Production Dockerfile
Create a `Dockerfile` in the root of the project:
```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies (including postgis/pgvector runtimes if needed)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Step 5.2: Build and Push Container to Amazon ECR
1. Log into your ECR registry (ECR URL is output by Terraform):
   ```bash
   aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin <aws_account_id>.dkr.ecr.us-east-1.amazonaws.com
   ```
2. Build the Docker image:
   ```bash
   docker build -t permit-rag-backend .
   ```
3. Tag the image:
   ```bash
   docker tag permit-rag-backend:latest <aws_account_id>.dkr.ecr.us-east-1.amazonaws.com/permit-rag-backend:latest
   ```
4. Push the image:
   ```bash
   docker push <aws_account_id>.dkr.ecr.us-east-1.amazonaws.com/permit-rag-backend:latest
   ```

### Step 5.3: Deploy to ECS Fargate
1. Update the ECS Service to retrieve the new image:
   ```bash
   aws ecs update-service --cluster permit-rag-cluster --service permit-rag-service --force-new-deployment
   ```

---

## Phase 6: Deploying the Frontend to S3 & CloudFront

### Step 6.1: Build Frontend Assets
1. Open the file `frontend/src/api.js` or create `frontend/.env.production` and configure the production API base url pointing to your CloudFront/ALB endpoint:
   ```env
   VITE_API_BASE_URL=https://api.yourdomain.com
   ```
2. Run build:
   ```bash
   cd frontend
   npm install
   npm run build
   ```
   *This outputs optimized, static assets into `frontend/dist/`.*

### Step 6.2: Upload to AWS S3
1. Sync files to the S3 bucket created by Terraform:
   ```bash
   aws s3 sync dist/ s3://<your-frontend-s3-bucket-name> --delete
   ```
2. Invalidate the CloudFront distribution to force edge caches to fetch your fresh files:
   ```bash
   aws cloudfront create-invalidation --distribution-id <cloudfront_distribution_id> --paths "/*"
   ```

---

## Phase 7: Verification & Testing
1. Visit the CloudFront domain URL (e.g., `https://dxxxxxxxxxx.cloudfront.net`).
2. Verify all routes function properly (Query, Documents, Upload).
3. Execute a RAG query to verify that PostgreSQL, Neo4j, and the Anthropic API integrate and function seamlessly in the cloud environment.
