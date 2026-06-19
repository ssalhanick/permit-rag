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

# Upgrade pip and install all third-party dependencies defined in pyproject.toml
RUN pip install --no-cache-dir --upgrade pip && \
    python -c "import tomllib, subprocess, sys; \
    deps = tomllib.load(open('pyproject.toml', 'rb'))['project']['dependencies']; \
    res = subprocess.run(['pip', 'install', '--no-cache-dir'] + deps); \
    sys.exit(res.returncode)"

# Pre-download the Hugging Face sentence-transformers embedding model.
# Since this runs immediately after requirements.txt installation, it will remain
# fully cached unless your requirements.txt changes, saving ~500MB of download/upload traffic.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('nomic-ai/nomic-embed-text-v1.5')"

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
