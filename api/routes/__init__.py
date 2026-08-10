"""
api/routes/__init__.py — Aggregate all route modules
=====================================================
Import routers here so main.py has a single include point.
"""

from api.routes.admin import router as admin_router
from api.routes.agents_admin import router as agents_admin_router
from api.routes.auth import router as auth_router
from api.routes.bids import router as bids_router
from api.routes.commerce import router as commerce_router
from api.routes.contractors import router as contractors_router
from api.routes.corpus import router as corpus_router
from api.routes.document_petitions import router as document_petitions_router
from api.routes.documents import router as documents_router
from api.routes.marketplace import router as marketplace_router
from api.routes.overlays import router as overlays_router
from api.routes.project_documents import router as project_documents_router
from api.routes.projects import router as projects_router
from api.routes.pull import router as pull_router
from api.routes.query import router as query_router
from api.routes.upload import router as upload_router
from api.routes.users import router as users_router

__all__ = [
    "admin_router",
    "agents_admin_router",
    "auth_router",
    "bids_router",
    "commerce_router",
    "contractors_router",
    "corpus_router",
    "document_petitions_router",
    "documents_router",
    "marketplace_router",
    "overlays_router",
    "project_documents_router",
    "projects_router",
    "pull_router",
    "query_router",
    "upload_router",
    "users_router",
]
