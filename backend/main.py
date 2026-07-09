# main.py — Subvox Pipeline (public engine)
"""FastAPI application for Subvox Pipeline — video subtitle processing."""

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from core.config import settings
from core.logging_setup import get_logger
from core.db import init_pool, close_pool

logger = get_logger(__name__)


async def lifespan(app: FastAPI):
    await init_pool()
    yield
    await close_pool()


app = FastAPI(
    title="Subvox Pipeline",
    description="Open-source video subtitle pipeline — download, transcribe, translate, burn.",
    version="0.1.0",
    docs_url="/docs",
    redoc_url=None,
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────
origins = [o.strip() for o in (settings.CORS_ORIGINS or "").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Pipeline routes ───────────────────────────────────────────
from api.jobs.public import router as jobs_public_router
from api.jobs.status import router as jobs_status_router
from api.jobs.subtitles import router as subtitles_router
from api.jobs.check_url import router as check_url_router
from api.jobs.economy_proxy import router as economy_proxy_router
from api.jobs.resolve import router as jobs_resolve_router
from api.stats import router as stats_router
from api.platforms import router as platforms_router

app.include_router(jobs_public_router, prefix="/jobs")
app.include_router(check_url_router, prefix="/jobs")
app.include_router(jobs_resolve_router, prefix="/jobs")
app.include_router(jobs_status_router, prefix="/jobs")
app.include_router(subtitles_router, prefix="/jobs")
app.include_router(economy_proxy_router, prefix="/jobs")
app.include_router(stats_router, prefix="/stats")
app.include_router(platforms_router)


# ── Proxy vers Economy (port 8001) ────────────────────────────
import httpx

ECONOMY_URL = settings.ECONOMY_URL

ECONOMY_PROXY_ROUTES = [
    "/auth/", "/billing/", "/rewards/", "/credentials/",
]


@app.api_route("/auth", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])
@app.api_route("/auth/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])
@app.api_route("/billing", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])
@app.api_route("/billing/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])
@app.api_route("/rewards", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])
@app.api_route("/rewards/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])
@app.api_route("/credentials", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])
@app.api_route("/credentials/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])
async def proxy_to_economy(request: Request, path: str = ""):
    """Forward auth/billing/rewards/credentials requests to Economy service."""
    url = f"{ECONOMY_URL}/{request.url.path.lstrip('/')}"
    if request.url.query:
        url += f"?{request.url.query}"
    body = await request.body()
    headers = {k: v for k, v in request.headers.items() if k.lower() not in ("host", "content-length")}
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.request(
            method=request.method,
            url=url,
            content=body,
            headers=headers,
        )
    return Response(content=resp.content, status_code=resp.status_code, headers=dict(resp.headers))


# ── Health check ──────────────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "ok", "service": "pipeline"}


# ── Serve local storage files (dev mode) ─────────────────────
import os as _os
from pathlib import Path as _Path
from fastapi.responses import FileResponse as _FileResponse


@app.get("/storage/{filename:path}")
async def serve_storage(filename: str):
    # Check pipeline/storage/ first
    base = _Path(_os.path.join(_os.path.dirname(__file__), "..", "storage")).resolve()
    fp = base / filename
    if fp.exists():
        return _FileResponse(str(fp), media_type="video/mp4")
    # Fallback to /tmp/subvox-output/
    alt = _Path("/tmp/subvox-output") / filename
    if alt.exists():
        return _FileResponse(str(alt), media_type="video/mp4")
    return {"error": "File not found"}, 404
