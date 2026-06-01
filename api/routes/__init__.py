"""
api/routes/__init__.py — Aggregate all route modules
=====================================================
Import routers here so main.py has a single include point.
"""

from api.routes.documents import router as documents_router
from api.routes.query import router as query_router
from api.routes.admin import router as admin_router

__all__ = ["query_router", "documents_router", "admin_router"]
