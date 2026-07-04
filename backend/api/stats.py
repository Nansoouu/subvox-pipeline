"""
api/stats.py — Public counters for the landing page hero.
"""

from fastapi import APIRouter
from core.db import get_conn
from core.logging_setup import get_logger

router = APIRouter()
logger = get_logger(__name__)


@router.post("/cta-click")
async def track_cta_click():
    """Track CTA button clicks (analytics placeholder)."""
    logger.info("CTA click tracked")
    return {"ok": True}


@router.post("/i18n-log")
async def log_i18n_error():
    """Log i18n missing keys (fire-and-forget from frontend)."""
    logger.info("i18n error logged")
    return {"ok": True}


@router.get("/counters")
async def get_counters():
    """Aggregated platform stats for the hero counters bar."""
    async with get_conn() as conn:
        row = await conn.fetchrow(
            """
            SELECT
                COALESCE((SELECT COUNT(*) FROM jobs), 0)::int               AS total_videos,
                COALESCE((SELECT COALESCE(SUM(duration_s), 0) FROM jobs), 0)::int
                                                                              AS total_duration_s,
                COALESCE((SELECT COUNT(DISTINCT target_lang)
                          FROM jobs WHERE target_lang IS NOT NULL), 0)::int   AS unique_languages,
                COALESCE((SELECT COUNT(DISTINCT user_id)
                          FROM jobs WHERE created_at >= now() - interval '24 hours'), 0)::int
                                                                              AS active_users_today,
                COALESCE((SELECT COUNT(*)
                          FROM jobs WHERE created_at >= now() - interval '24 hours'), 0)::int
                                                                              AS today_videos
            """
        )

    total = row["total_videos"]
    today = row["today_videos"]

    # Simple trend: ratio of today vs daily average (last 7 days)
    trend_pct = 0
    if total > 0:
        async with get_conn() as conn:
            week_ago = await conn.fetchval(
                "SELECT COUNT(*)::int FROM jobs WHERE created_at >= now() - interval '7 days'"
            )
        daily_avg = week_ago / 7 if week_ago else 1
        trend_pct = round(((today / daily_avg) - 1) * 100) if daily_avg > 0 else 0

    return {
        "total_videos": total,
        "total_duration_s": row["total_duration_s"],
        "unique_languages": row["unique_languages"],
        "active_users_today": row["active_users_today"],
        "today_videos": today,
        "trend_pct": trend_pct,
    }
