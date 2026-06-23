# Use official Python 3.11 slim runtime as parent image
FROM python:3.11-slim

# Install system dependencies (build tools for compilation, Postgres client library, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy pyproject.toml to read dependencies
COPY pyproject.toml ./

# Upgrade pip and install CPU-only PyTorch first (avoids downloading 800MB+ CUDA packages)
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

# Install the rest of the dependencies defined in pyproject.toml
RUN python -c "import tomllib, subprocess, sys; \
    deps = tomllib.load(open('pyproject.toml', 'rb'))['project']['dependencies']; \
    res = subprocess.run(['pip', 'install', '--no-cache-dir'] + deps); \
    sys.exit(res.returncode)"

# Pre-download the Hugging Face sentence-transformers embedding and NLI models.
# Since this runs immediately after requirements.txt installation, it will remain
# fully cached unless your requirements.txt changes, saving ~600MB of download/upload traffic.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('nomic-ai/nomic-embed-text-v1.5')" && \
    python -c "from transformers import pipeline; pipeline('zero-shot-classification', model='cross-encoder/nli-deberta-v3-small')"

# Copy project metadata and code files (invalidates cache only for code changes)
COPY pyproject.toml README.md ./
COPY api/ ./api
COPY db/ ./db
COPY rag/ ./rag
COPY ingestion/ ./ingestion
COPY audit/ ./audit
COPY evaluation/ ./evaluation

# Install the local project package without reinstalling dependencies
RUN pip install --no-cache-dir hatchling && \
    pip install --no-cache-dir --no-deps .

# Expose FastAPI default port
EXPOSE 8000

# Start command running Uvicorn
CMD ["python", "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
