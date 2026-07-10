"""
api/jobs/public.py — Public job feed (transparency page)
"""

from fastapi import APIRouter, Depends, Query
from core.db import get_conn
from core.logging_setup import get_logger
from api.auth import get_current_user_optional

import json

router = APIRouter()
logger = get_logger(__name__)

SOURCE_DOMAINS = {
    "youtube.com": "YouTube",
    "youtu.be": "YouTube",
    "x.com": "X / Twitter",
    "twitter.com": "X / Twitter",
    "tiktok.com": "TikTok",
    "instagram.com": "Instagram",
    "vimeo.com": "Vimeo",
    "dailymotion.com": "Dailymotion",
}


def _source_label(url: str) -> str:
    """Extract platform name from URL."""
    for domain, label in SOURCE_DOMAINS.items():
        if domain in url:
            return label
    return "Web"


@router.get("/search")
async def search_jobs(
    source_url_like: str = Query(""),
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """Recherche des jobs par source_url (LIKE)."""
    if not source_url_like:
        return {"jobs": [], "total": 0}

    async with get_conn() as conn:
        rows = await conn.fetch(
            """
            SELECT id, source_url, target_lang, status, title,
                   duration_s, created_at, updated_at, thumbnail_url
            FROM jobs
            WHERE source_url ILIKE $1
            ORDER BY created_at DESC
            LIMIT $2 OFFSET $3
            """,
            f"%{source_url_like}%",
            limit,
            offset,
        )

    results = [
        {
            "job_id": str(r["id"]),
            "source_url": r["source_url"],
            "target_lang": r["target_lang"],
            "status": r["status"],
            "title": r["title"],
            "duration_s": r["duration_s"],
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None,
            "thumbnail_url": r["thumbnail_url"],
        }
        for r in rows
    ]

    return {"jobs": results, "total": len(results)}


@router.get("/feed")
async def get_public_jobs(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    user=Depends(get_current_user_optional),
):
    """
    Public job feed — une ligne par langue.
    Accessible sans auth. Si l'utilisateur est connecte,
    on renvoie son user_id pour qu'il sache quels jobs lui appartiennent.
    """
    current_wallet = str(user["id"]) if user and user.get("id") else None

    async with get_conn() as conn:
        rows = await conn.fetch(
            """
            SELECT
                j.id AS job_id,
                j.source_url,
                j.target_lang,
                j.status,
                j.mode,
                j.created_at,
                j.updated_at,
                COALESCE(j.duration_s, 0) AS video_duration_s,
                j.user_id,
                j.visitor_token
            FROM jobs j
            WHERE j.status IN ('queued', 'processing', 'done', 'error')
              AND j.target_lang IS NOT NULL
              AND j.target_lang != 'none'
              AND j.archived_at IS NULL
            ORDER BY j.created_at DESC
            OFFSET $1 LIMIT $2
            """,
            offset,
            limit,
        )

    results = []
    for row in rows:
        # Detecter le proprietaire via user_id (wallet address)
        wallet_in_db = row.get("user_id")
        is_owner = bool(current_wallet and wallet_in_db and current_wallet.lower() == wallet_in_db.lower())
        results.append({
            "job_id": str(row["job_id"]),
            "short_id": str(row["job_id"])[:8],
            "source": _source_label(row["source_url"]),
            "source_url": row["source_url"] if is_owner else None,  # hide URL for non-owners
            "target_lang": row["target_lang"],
            "status": row["status"],
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            "completed_at": row["updated_at"].isoformat() if row["updated_at"] else None,
            "duration_s": int(row["video_duration_s"] or 0),
            "groq_source": "community",
            "groq_time_s": 0,
            "cost_subvox": 0,  # on-chain, removed from DB
            "cost_split": {},  # on-chain, removed from DB
            "mode": row["mode"],
            "is_owner": is_owner,
            "owner_short": (wallet_in_db[:6] + "..." if wallet_in_db else
                           str(row["user_id"])[:8] if row["user_id"] else None),
            "owner_wallet": wallet_in_db,
            "visitor": bool(row["visitor_token"] and not row["user_id"]),
            "visibility": row.get("visibility") or "public",
            "total_time_s": int((row["updated_at"] - row["created_at"]).total_seconds()) if row["created_at"] and row["updated_at"] else None,
            "provider_wallet_short": None,  # on-chain
            "subtest_tx": None,  # on-chain
        })

    return {"jobs": results, "total": len(results), "offset": offset, "limit": limit}
