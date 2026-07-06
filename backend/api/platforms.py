"""
api/platforms.py — Endpoints pour les plateformes supportées (yt-dlp).
"""

from fastapi import APIRouter, Query
from core.db import get_conn
from core.logging_setup import get_logger

router = APIRouter()
logger = get_logger(__name__)


@router.get("/platforms")
async def list_platforms(
    status: str | None = None,
    content_type: str | None = None,
    limit: int = Query(default=100, le=5000),
    offset: int = Query(default=0, ge=0),
):
    """Liste toutes les plateformes supportées, avec filtres optionnels."""
    conditions = []
    params: list = []
    idx = 1

    if status and status != "all":
        conditions.append(f"status = ${idx}")
        params.append(status)
        idx += 1

    if content_type and content_type != "all":
        conditions.append(f"content_type = ${idx}")
        params.append(content_type)
        idx += 1

    where = ""
    if conditions:
        where = "WHERE " + " AND ".join(conditions)

    async with get_conn() as conn:
        count = await conn.fetchval(f"SELECT COUNT(*) FROM platforms {where}", *params)
        rows = await conn.fetch(
            f"""
            SELECT slug, name, status, content_type, website,
                   yt_dlp_extractor, importance, video_count,
                   is_active
            FROM platforms
            {where}
            ORDER BY importance DESC, name ASC
            LIMIT ${idx} OFFSET ${idx + 1}
            """,
            *params, limit, offset,
        )

    platforms = [
        {
            "slug": r["slug"],
            "name": r["name"],
            "status": r["status"],
            "content_type": r["content_type"],
            "website": r["website"],
            "yt_dlp_extractor": r["yt_dlp_extractor"],
            "importance": max(1, min(5, round(r["importance"] / 20))),  # normalize 0-100 to 1-5
            "video_count": r["video_count"],
            "is_active": r["is_active"],
        }
        for r in rows
    ]

    return {
        "platforms": platforms,
        "total": count,
        "offset": offset,
        "limit": limit,
    }


@router.get("/platforms/{slug}")
async def get_platform(slug: str):
    """Détail d'une plateforme par son slug."""
    async with get_conn() as conn:
        row = await conn.fetchrow(
            "SELECT slug, name, name_en, status, content_type, website, "
            "yt_dlp_extractor, importance, video_count, is_active, "
            "seo_title, seo_title_en, icon_url, "
            "created_at, updated_at "
            "FROM platforms WHERE slug = $1",
            slug,
        )

    if not row:
        return {"error": "Platform not found"}, 404

    return dict(row)


@router.get("/platforms/{slug}/health")
async def get_platform_health(slug: str):
    """Santé d'une plateforme basée sur les URLs de référence testées."""
    async with get_conn() as conn:
        # Dernier statut
        platform = await conn.fetchrow(
            "SELECT slug, name, status, content_type, importance FROM platforms WHERE slug = $1",
            slug,
        )
        if not platform:
            return {"error": "Platform not found"}, 404

        # URLs de référence
        test_urls = await conn.fetch(
            "SELECT id, video_type, url, status, last_http_code, last_checked_at, job_id, created_at "
            "FROM platform_test_urls WHERE platform_slug = $1 "
            "ORDER BY created_at DESC LIMIT 20",
            slug,
        )

        # Stats
        stats = await conn.fetchrow(
            """SELECT
                COUNT(*)::int AS total,
                COUNT(*) FILTER (WHERE status = 'verified')::int AS verified,
                COUNT(*) FILTER (WHERE status = 'broken')::int AS broken,
                COUNT(*) FILTER (WHERE status = 'pending')::int AS pending,
                MAX(last_checked_at) AS last_check
               FROM platform_test_urls WHERE platform_slug = $1""",
            slug,
        )

        # Dernières missions associées
        missions = await conn.fetch(
            "SELECT slug, title, reward_amount, reward_currency, starts_at, ends_at, is_active "
            "FROM missions WHERE mission_type = 'platform_test' AND requirements->>'platform_slug' = $1 "
            "ORDER BY created_at DESC LIMIT 6",
            slug,
        )

    return {
        "platform": dict(platform),
        "health": dict(stats),
        "test_urls": [dict(r) for r in test_urls],
        "missions": [dict(r) for r in missions],
    }


@router.post("/platforms/{slug}/test")
async def test_platform(slug: str):
    """Stub: marquer une plateforme comme testée."""
    async with get_conn() as conn:
        await conn.execute(
            "UPDATE platforms SET status = 'active' WHERE slug = $1 AND status = 'untested'",
            slug,
        )
    return {"ok": True, "slug": slug}
