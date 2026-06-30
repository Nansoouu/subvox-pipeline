"""security_middleware.py — Placeholder. Full security blocks in subvox-confidential."""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
import logging

logger = logging.getLogger(__name__)

class SecurityScanBlocker(BaseHTTPMiddleware):
    """No-op middleware — blocks malicious scans when subvox-confidential is loaded."""
    async def dispatch(self, request: Request, call_next):
        return await call_next(request)
