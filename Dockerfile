FROM python:3.11-slim

WORKDIR /app

# System deps for psycopg and native wheels
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./

# Install PyTorch CPU before sentence-transformers
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

# Install project dependencies from pyproject.toml
RUN python -c "import tomllib, subprocess, sys; \
    deps = tomllib.load(open('pyproject.toml', 'rb'))['project']['dependencies']; \
    res = subprocess.run(['pip', 'install', '--no-cache-dir'] + deps); \
    sys.exit(res.returncode)"

# Pre-download models (baked into image layer for faster ECS startup)
ENV HF_HOME=/app/.cache/huggingface
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('nomic-ai/nomic-embed-text-v1.5')" && \
    python -c "from transformers import pipeline; pipeline('zero-shot-classification', model='cross-encoder/nli-deberta-v3-small')"

COPY pyproject.toml README.md ./
COPY api/ ./api
COPY db/ ./db
COPY rag/ ./rag
COPY ingestion/ ./ingestion
COPY audit/ ./audit
COPY evaluation/ ./evaluation

RUN pip install --no-cache-dir hatchling && \
    pip install --no-cache-dir --no-deps .

# Non-sensitive Cognito config — baked in so ECS works without manual task-def vars.
# Rotate by rebuilding the image; no secrets here (pool ID + region are public).
ENV COGNITO_USER_POOL_ID=us-east-1_HF3i1xgNF
ENV COGNITO_REGION=us-east-1

EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
