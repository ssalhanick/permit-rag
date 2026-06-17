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
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.routes import admin_router, documents_router, query_router, upload_router
from api.schemas import HealthResponse
from db.client import close_pool, ping
from db import graph_client as _graph_client

log = logging.getLogger(__name__)


def _parse_cors_origins() -> list[str]:
    """Return CORS origins from env, defaulting to local dev origins."""
    if os.environ.get("API_CORS_ALLOW_ALL", "false").strip().lower() in {"1", "true", "yes", "on"}:
        return ["*"]
    raw = os.environ.get(
        "API_CORS_ALLOW_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173,http://127.0.0.1:5173",
    )
    origins = [value.strip() for value in raw.split(",") if value.strip()]
    return origins or ["http://localhost:3000"]


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


# ── CORS (env-driven allowlist) ──────────────────────────────

cors_origins = _parse_cors_origins()
allow_all_origins = cors_origins == ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=not allow_all_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Include routers ──────────────────────────────────────────

app.include_router(query_router)
app.include_router(documents_router)
app.include_router(admin_router)
app.include_router(upload_router)


# ── Error handling (uniform payload shape) ───────────────────


@app.exception_handler(RequestValidationError)
def handle_validation_error(
    _request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Return compact validation errors using the shared detail shape."""
    first = exc.errors()[0] if exc.errors() else {}
    loc = ".".join(str(part) for part in first.get("loc", []))
    msg = first.get("msg", "Invalid request payload.")
    detail = f"Validation error at {loc}: {msg}" if loc else f"Validation error: {msg}"
    return JSONResponse(status_code=422, content={"detail": detail})


@app.exception_handler(HTTPException)
def handle_http_exception(_request: Request, exc: HTTPException) -> JSONResponse:
    """Normalize HTTPException detail into a single detail string."""
    raw = exc.detail
    if isinstance(raw, str):
        detail = raw
    else:
        detail = str(raw)
    return JSONResponse(status_code=exc.status_code, content={"detail": detail})


# ── Health endpoint (lives on main app, not a router) ────────


@app.get(
    "/health",
    response_model=HealthResponse,
    tags=["system"],
    summary="Health check",
    description="Returns service status, database connectivity, and graph layer health.",
)
def health_check() -> HealthResponse:
    """Check API, database, and graph (Neo4j) health.

    Overall status is driven by Postgres connectivity only.
    graph_health is additive — Neo4j being unreachable does NOT flip
    the service to 'unhealthy'; it merely surfaces graph_health=False.
    """
    db_ok = ping()
    # Non-blocking graph ping — catches all exceptions internally
    graph_ok = _graph_client.ping()
    return HealthResponse(
        status="healthy" if db_ok else "unhealthy",
        database=db_ok,
        graph_health=graph_ok,
        version="0.1.0",
    )
