"""
api/jobs/resolve.py — Slug → job_id resolution for SEO-friendly URLs.

Route: GET /jobs/resolve/{slug}

Resolves a per-language slug to a job_id + lang pair by scanning
seo_metadata JSONB for a matching slug field.
"""

from fastapi import APIRouter, HTTPException
from core.logging_setup import get_logger

logger = get_logger(__name__)

router = APIRouter()


@router.get("/resolve/{slug:str}")
async def resolve_slug(slug: str) -> dict:
    """
    Resolve a per-language slug to (job_id, lang).

    Searches jobs.seo_metadata JSONB for any language entry whose 'slug'
    field matches the given slug. Returns the job_id and the matching
    language code, or 404 if not found.
    """
    if not slug or not slug.strip():
        raise HTTPException(status_code=400, detail="Slug is required")

    slug = slug.strip().lower()

    try:
        from core.db import direct_connect as _direct
        from uuid import UUID

        async with _direct() as conn:
            # Parcourir seo_metadata JSONB pour trouver le slug
            row = await conn.fetchrow(
                """
                SELECT id, lang, seo_metadata->>lang AS entry_json
                FROM (
                    SELECT id, jsonb_object_keys(seo_metadata) AS lang
                    FROM jobs
                    WHERE seo_metadata IS NOT NULL
                      AND seo_metadata::text ILIKE '%' || $1 || '%'
                ) langs
                JOIN jobs j ON j.id = langs.id
                WHERE j.seo_metadata->langs.lang->>'slug' = $1
                LIMIT 1
                """,
                slug,
            )

            if not row:
                logger.info("Slug non trouve: %s", slug)
                raise HTTPException(status_code=404, detail=f"Slug '{slug}' not found")

            job_id = str(row["id"])
            lang = str(row["lang"])

            logger.info(
                "Slug resolve: %s → job=%s lang=%s",
                slug,
                job_id[:8],
                lang,
            )

            return {
                "job_id": job_id,
                "lang": lang,
                "slug": slug,
            }

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "Resolution slug echouee: %s",
            exc,
            extra={"slug": slug},
        )
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/slugs")
async def list_all_slugs() -> list[dict]:
    """
    Retourne tous les slugs SEO (toutes langues) pour tous les jobs.
    Utilise par le sitemap pour generer les entrees watch pages.
    """
    try:
        from core.db import direct_connect as _direct
        from uuid import UUID

        async with _direct() as conn:
            rows = await conn.fetch(
                """
                SELECT id, seo_metadata
                FROM jobs
                WHERE seo_metadata IS NOT NULL
                  AND seo_metadata != '{}'::jsonb
                  AND status = 'done'
                ORDER BY updated_at DESC
                LIMIT 1000
                """
            )

            results: list[dict] = []
            for row in rows:
                job_id = str(row["id"])
                seo = row["seo_metadata"]

                if isinstance(seo, str):
                    import json as _json
                    try:
                        seo = _json.loads(seo)
                    except Exception:
                        continue

                if not isinstance(seo, dict):
                    continue

                slugs_by_lang: dict[str, str] = {}
                for lang_code, entry in seo.items():
                    if isinstance(entry, dict) and entry.get("slug"):
                        slugs_by_lang[lang_code] = entry["slug"]

                if slugs_by_lang:
                    results.append({
                        "job_id": job_id,
                        "slugs": slugs_by_lang,
                    })

            logger.info("Liste slugs: %d jobs avec slugs", len(results))
            return results

    except Exception as exc:
        logger.error(
            "Liste slugs echouee: %s",
            exc,
        )
        return []
