"""
api/routes/__init__.py — Aggregate all route modules
=====================================================
Import routers here so main.py has a single include point.
"""

from api.routes.admin import router as admin_router
from api.routes.auth import router as auth_router
from api.routes.documents import router as documents_router
from api.routes.projects import router as projects_router
from api.routes.query import router as query_router
from api.routes.upload import router as upload_router

__all__ = [
    "admin_router",
    "auth_router",
    "documents_router",
    "projects_router",
    "query_router",
    "upload_router",
]
