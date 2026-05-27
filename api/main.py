"""
api/main.py — FastAPI application entry point
===============================================
Creates the app, registers routes, configures middleware,
and provides the GET /health endpoint.

Run locally:
    uvicorn api.main:app --reload --port 8000

Or:
    py -m uvicorn api.main:app --reload --port 8000
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import query_router
from api.schemas import HealthResponse
from db.client import close_pool, ping

log = logging.getLogger(__name__)


# ── Lifespan (startup / shutdown) ────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Load .env on startup, close DB pool on shutdown."""
    load_dotenv()
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    )
    log.info("permit_rag API starting up")
    yield
    close_pool()
    log.info("permit_rag API shut down")


# ── App factory ──────────────────────────────────────────────

app = FastAPI(
    title="permit_rag API",
    version="0.1.0",
    description=(
        "RAG-powered construction permit compliance tool for the DFW market. "
        "Query municipal codes, Texas state regulations, and federal standards "
        "with cited answers."
    ),
    lifespan=lifespan,
)


# ── CORS (permissive for local dev — tighten for production) ─

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Include routers ──────────────────────────────────────────

app.include_router(query_router)


# ── Health endpoint (lives on main app, not a router) ────────


@app.get(
    "/health",
    response_model=HealthResponse,
    tags=["system"],
    summary="Health check",
    description="Returns service status and database connectivity.",
)
def health_check() -> HealthResponse:
    """Check API and database health."""
    db_ok = ping()
    return HealthResponse(
        status="healthy" if db_ok else "unhealthy",
        database=db_ok,
        version="0.1.0",
    )
