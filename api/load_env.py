"""
api/load_env.py — Environment bootstrap for local vs production
==============================================================
Load order (local laptop):
  1. `.env.local` — Docker Postgres, CORS, Neo4j, local URLs
  2. `.env` — shared secrets (API keys, JWT, admin token)

Production (ECS):
  Terraform/SSM inject vars — no dotenv files in the container.
  Detected via ENVIRONMENT=production or ECS metadata.

Optional: `.env.production` on laptop for debugging against RDS
(set ENVIRONMENT=production before starting uvicorn).
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def resolve_environment() -> str:
    """Return ``local`` or ``production`` without reading dotenv files."""
    if os.environ.get("AWS_EXECUTION_ENV") or os.environ.get("ECS_CONTAINER_METADATA_URI_V4"):
        return "production"

    explicit = os.environ.get("ENVIRONMENT", "").strip().lower()
    if explicit in {"production", "prod"}:
        return "production"
    if explicit in {"local", "development", "dev"}:
        return "local"
    return "local"


def bootstrap_env() -> str:
    """Load dotenv files for the active profile. Returns resolved profile."""
    profile = resolve_environment()

    if profile == "local":
        load_dotenv(PROJECT_ROOT / ".env.local", override=True)
    else:
        prod_file = PROJECT_ROOT / ".env.production"
        if prod_file.exists():
            load_dotenv(prod_file, override=True)

    load_dotenv(PROJECT_ROOT / ".env", override=True)

    if profile == "local":
        os.environ.setdefault("ENVIRONMENT", "local")
    else:
        os.environ.setdefault("ENVIRONMENT", "production")

    return profile
