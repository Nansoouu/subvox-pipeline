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
from api.jobs.submit import router as jobs_submit_router
from api.jobs.subtitles import router as subtitles_router
from api.jobs.check_url import router as check_url_router
from api.jobs.resolve import router as jobs_resolve_router
from api.jobs.upload import router as jobs_upload_router
from api.jobs.dispatch import router as jobs_dispatch_router
from api.stats import router as stats_router
from api.platforms import router as platforms_router
from api.auth_router import router as auth_router
from api.stripe_router import router as stripe_router

from api.bodacc import router as bodacc_router

app.include_router(jobs_public_router, prefix="/jobs")
app.include_router(check_url_router, prefix="/jobs")
app.include_router(jobs_resolve_router, prefix="/jobs")
app.include_router(jobs_submit_router, prefix="/jobs")
app.include_router(jobs_status_router, prefix="/jobs")
app.include_router(subtitles_router, prefix="/jobs")
app.include_router(jobs_upload_router, prefix="/jobs")
app.include_router(jobs_dispatch_router, prefix="/internal")
app.include_router(stats_router, prefix="/stats")
app.include_router(platforms_router)
app.include_router(auth_router)
app.include_router(stripe_router)
app.include_router(bodacc_router)


# ── Solana RPC Proxy (évite les CORS navigateur) ──────────────
import httpx as _httpx

@app.post("/solana-rpc")
async def proxy_solana_rpc(request: Request):
    """Proxy les appels RPC Solana depuis le navigateur (évite CORS 403)."""
    body = await request.body()
    async with _httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            "https://api.mainnet-beta.solana.com",
            content=body,
            headers={"Content-Type": "application/json"},
        )
    return Response(content=resp.content, status_code=resp.status_code)


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
