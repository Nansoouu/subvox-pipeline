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
                j.created_at,
                j.updated_at,
                COALESCE(j.duration_s, 0) AS video_duration_s,
                j.user_id,
                j.visitor_token,
                j.cost_breakdown
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
        # Parse cost_breakdown (asyncpg retourne les JSONB en str)
        cb = row.get("cost_breakdown")
        if isinstance(cb, str):
            try:
                cb = json.loads(cb)
            except (json.JSONDecodeError, TypeError):
                cb = None
        cb_dict = cb if isinstance(cb, dict) else None

        # Detecter le proprietaire via le wallet dans cost_breakdown ou user_id
        wallet_in_db = None
        if cb_dict:
            wallet_in_db = cb_dict.get("wallet")
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
            "cost_subvox": int(cb_dict.get("user_cost", cb_dict.get("total_gross", 0))) if cb_dict else 0,
            "cost_split": {
                "total": cb_dict.get("user_cost", cb_dict.get("total_gross", 0)),
                "provider": cb_dict.get("provider_share", 0),
                "platform": cb_dict.get("platform_share", 0),
                "rewards": cb_dict.get("rewards_share", 0),
                "burn": cb_dict.get("burn_amount", 0),
            } if cb_dict else None,
            "is_owner": is_owner,
            "owner_short": (wallet_in_db[:6] + "..." if wallet_in_db else
                           str(row["user_id"])[:8] if row["user_id"] else None),
            "owner_wallet": wallet_in_db,
            "visitor": bool(row["visitor_token"] and not row["user_id"]),
            "visibility": row.get("visibility") or "public",
            "total_time_s": int((row["updated_at"] - row["created_at"]).total_seconds()) if row["created_at"] and row["updated_at"] else None,
            "provider_wallet_short": (cb_dict.get("provider_wallet", "")[:6] + "..." if cb_dict and cb_dict.get("provider_wallet") else None),
        })

    return {"jobs": results, "total": len(results), "offset": offset, "limit": limit}
