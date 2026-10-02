"""Versioned API router (section 57)."""

from fastapi import APIRouter

from app.api.v1 import auth, catalog, credentials, governance, organizations, runs, search

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(organizations.router)
api_router.include_router(credentials.router)
api_router.include_router(search.router)
api_router.include_router(runs.router)
api_router.include_router(catalog.router)
api_router.include_router(governance.router)

__all__ = ["api_router"]
