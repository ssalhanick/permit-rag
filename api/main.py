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

if os.environ.get("AWS_LAMBDA_FUNCTION_NAME") is None:
    from api.load_env import bootstrap_env

    bootstrap_env()
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.routes import (
    admin_router,
    agents_admin_router,
    auth_router,
    bids_router,
    commerce_router,
    contractors_router,
    corpus_router,
    document_petitions_router,
    documents_router,
    marketplace_router,
    overlays_router,
    project_documents_router,
    projects_router,
    pull_router,
    query_router,
    upload_router,
    users_router,
)
from api.schemas import HealthResponse
from db import graph_client as _graph_client
from db.client import close_pool, ping

log = logging.getLogger(__name__)


# ── Dependency-injected agents ───────────────────────────────
# rag/ may not import ingestion/, commerce/, forms/, or bids/ (AGENTS.md), so
# agents backed by those packages are registered here at startup — api/ is the
# one layer allowed to import everything. The callable is bound lazily so this
# import stays cheap; the heavy module loads only when the agent actually runs.


def _register_di_agents() -> None:
    """Register cross-boundary agents in the shared registry (idempotent)."""
    from rag.agent_runtime import Tier
    from rag.agents.registry import AgentSpec, lazy, register

    register(
        AgentSpec(
            name="metadata_validator",
            callable=lazy("ingestion.metadata_agent", "validate_document"),
            tier=Tier.MID,  # content-vs-metadata inference is a sonnet-class task
            parallel_safe=True,  # documents validate independently
            metrics=("metadata_field_precision", "date_extraction_accuracy",
                     "false_flag_rate"),
        ),
        replace=True,
    )
    register(
        AgentSpec(
            name="bid_evaluator",
            callable=lazy("bids.evaluator", "evaluate_bid"),
            tier=Tier.MID,
            parallel_safe=True,  # bids evaluate independently
            metrics=("field_accuracy", "red_flag_precision_recall", "price_mape"),
        ),
        replace=True,
    )


_register_di_agents()

LOCALHOST_CORS_REGEX = r"https?://(localhost|127\.0\.0\.1)(:\d+)?"


def _env_bool(name: str, default: bool = False) -> bool:
    """Parse boolean environment variable values."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _parse_cors_origins() -> list[str]:
    """Return CORS origins from env, defaulting to local dev origins."""
    if os.environ.get("API_CORS_ALLOW_ALL", "false").strip().lower() in {"1", "true", "yes", "on"}:
        return ["*"]
    raw = os.environ.get(
        "API_CORS_ALLOW_ORIGINS",
        (
            "http://localhost:3000,http://127.0.0.1:3000,"
            "http://localhost:5173,http://127.0.0.1:5173,"
            "http://localhost:5174,http://127.0.0.1:5174,"
            "http://localhost:5175,http://127.0.0.1:5175,"
            "http://localhost:5176,http://127.0.0.1:5176"
        ),
    )
    origins = [value.strip() for value in raw.split(",") if value.strip()]
    return origins or ["http://localhost:3000"]


def _cors_middleware_kwargs() -> dict[str, object]:
    """Build CORSMiddleware kwargs from environment."""
    if _env_bool("API_CORS_ALLOW_ALL"):
        return {
            "allow_origins": ["*"],
            "allow_credentials": False,
            "allow_methods": ["*"],
            "allow_headers": ["*"],
        }
    if _env_bool("API_CORS_ALLOW_LOCALHOST"):
        return {
            "allow_origin_regex": LOCALHOST_CORS_REGEX,
            "allow_credentials": True,
            "allow_methods": ["*"],
            "allow_headers": ["*"],
        }
    origins = _parse_cors_origins()
    return {
        "allow_origins": origins,
        "allow_credentials": True,
        "allow_methods": ["*"],
        "allow_headers": ["*"],
    }


# ── Lifespan (startup / shutdown) ────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Configure logging on startup and close DB pool on shutdown."""
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    )
    db_url = os.environ.get("DATABASE_URL", "")
    db_host = db_url.split("@")[-1].split("/")[0] if "@" in db_url else "not set"
    log.info("permit_rag API starting up — DB host: %s", db_host)
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

app.add_middleware(CORSMiddleware, **_cors_middleware_kwargs())


# ── Include routers (namespaced under /api for CloudFront SPA separation) ──

api_router = APIRouter(prefix="/api")
api_router.include_router(query_router)
api_router.include_router(document_petitions_router)
api_router.include_router(documents_router)
api_router.include_router(admin_router)
api_router.include_router(agents_admin_router)
api_router.include_router(upload_router)
api_router.include_router(pull_router)
api_router.include_router(auth_router)
api_router.include_router(overlays_router)
api_router.include_router(project_documents_router)
api_router.include_router(projects_router)
api_router.include_router(commerce_router)
api_router.include_router(contractors_router)
api_router.include_router(marketplace_router)
api_router.include_router(bids_router)
api_router.include_router(corpus_router)
api_router.include_router(users_router)
app.include_router(api_router)


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


@app.exception_handler(Exception)
def handle_unexpected_error(_request: Request, exc: Exception) -> JSONResponse:
    """Catch-all: log the traceback and return 500 with detail visible to caller."""
    log.exception("Unhandled exception: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"detail": f"{type(exc).__name__}: {exc}"},
    )


# ── Health endpoint (lives on main app, not a router) ────────


@app.get(
    "/health",
    response_model=HealthResponse,
    tags=["system"],
    summary="Health check",
    description="Returns service status, database connectivity, and graph layer health.",
)
@app.get(
    "/api/health",
    response_model=HealthResponse,
    tags=["system"],
    include_in_schema=False,
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
