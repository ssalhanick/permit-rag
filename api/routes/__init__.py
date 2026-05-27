"""
api/routes/__init__.py — Aggregate all route modules
=====================================================
Import routers here so main.py has a single include point.
"""

from api.routes.query import router as query_router

__all__ = ["query_router"]
