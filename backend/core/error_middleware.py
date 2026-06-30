"""error_middleware.py — Placeholder. Full BugCapture in subvox-confidential."""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
import logging

logger = logging.getLogger(__name__)

class BugCaptureMiddleware(BaseHTTPMiddleware):
    """No-op middleware — sends errors to Sentry when subvox-confidential is loaded."""
    async def dispatch(self, request: Request, call_next):
        return await call_next(request)
