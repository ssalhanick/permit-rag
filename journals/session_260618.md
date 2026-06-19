# Session Log: 2026-06-18

## Objectives
Bootstrap, debug, and successfully deploy the production AWS infrastructure, database schema, containerized FastAPI backend, and React static frontend.

## Accomplishments

### 1. Database Tier & Bootstrapping
*   **RDS Accessibility**: Moved the RDS PostgreSQL database subnet group to public subnets, enabled public accessibility on the instance, and added a temporary security group rule for port `5432` to allow external connection bootstrapping from the local development machine.
*   **Migration Constraint Fix**: Removed seed-level `INSERT` statements from the schema migration file `008_municipal_boundaries_pilot.sql` and moved them to a dedicated seed file `db/seeds/municipal_boundaries.sql`. This avoids foreign key failures during clean deployments since seeds run after all migrations have completed.
*   **Idempotent Init Script**: Enhanced `scripts/init_rds_db.py` to automatically execute `DROP SCHEMA public CASCADE; CREATE SCHEMA public;` at startup. This enables clean, conflict-free retries by wiping partially initialized states.

### 2. Backend Containerization
*   **Dockerfile Creation**: Created a production-grade `Dockerfile` in the project root utilizing `python:3.11-slim`. 
*   **Build Packaging**: Configured the build to copy all python source directories and `README.md` before executing `pip install .` to satisfy the Hatchling build requirements.
*   **Model Caching**: Pre-cached the `nomic-ai/nomic-embed-text-v1.5` sentence-transformers embedding model inside the Docker image during construction. This prevents container tasks from downloading the 500MB model over the network at runtime, accelerating task startup and scaling.

### 3. Deploy Script Hardening (`scripts/deploy.ps1`)
*   **ECR Pipeline Encoding**: Routed ECR authentication through `cmd.exe /c` to bypass PowerShell's pipeline UTF-16 encoding bug which corrupted credentials and threw `400 Bad Request` errors.
*   **String Interpolation Fix**: Wrapped the `$ecrRepoUri` variable in curly braces (`${ecrRepoUri}`) in tagging and pushing commands to prevent PowerShell from interpreting the tag colon (`:`) as a scope modifier.
*   **Interactive Pager Bypass**: Explicitly set `$env:AWS_PAGER = ""` at the start of the script to prevent AWS CLI JSON output from blocking script execution with interactive pagers.

### 4. Code Cleanup & Documentation
*   **Workspace Organization**: Moved `dev.ps1` and `stop.ps1` into the `scripts/` folder to clean up the project root. Updated script paths inside `package.json` to keep `npm start` and `npm run stop` operational.
*   **Documentation**: Created a detailed **AWS Production Deployment** section in `README.md` covering architecture, prerequisites, database seeding, and update scripts.

## Outcome
The entire stack has been successfully deployed to AWS. The backend container is running on ECS Fargate behind the ALB, and the frontend is served via CloudFront CDN. The custom domain **`permits.scottsalhanick.com`** is fully operational and securely served via ACM SSL.
