# Use official Python 3.11 slim runtime as parent image
FROM python:3.11-slim

# Install system dependencies (build tools for compilation, Postgres client library, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy project metadata files (Hatchling requires README.md since it is defined in pyproject.toml)
COPY pyproject.toml requirements.txt README.md ./

# Copy all application directories (Hatchling requires these packages to compile the wheel)
COPY api/ ./api
COPY db/ ./db
COPY rag/ ./rag
COPY ingestion/ ./ingestion
COPY audit/ ./audit
COPY evaluation/ ./evaluation

# Upgrade pip, install build backend (hatchling), and compile/install the project and its dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir hatchling && \
    pip install --no-cache-dir .

# Pre-download the Hugging Face sentence-transformers embedding model
# to ensure faster container startup and avoid network requests at runtime
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('nomic-ai/nomic-embed-text-v1.5')"

# Expose FastAPI default port
EXPOSE 8000

# Start command running Uvicorn
CMD ["python", "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
