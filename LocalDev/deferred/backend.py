"""
Thin re-export for backward compatibility / Vercel entry point.

Usage:
    uvicorn backend:app --reload
    (or reference api.index:app directly)
"""

from api.index import app  # noqa: F401
