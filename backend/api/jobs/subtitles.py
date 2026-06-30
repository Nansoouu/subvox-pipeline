"""
api/jobs/subtitles.py — Endpoints sous-titres (VTT, transcription, traduction)
"""

from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, HTTPException, Request

from core.db import get_conn
from core.logging_setup import get_logger

logger = get_logger(__name__)

router = APIRouter()


@router.get("/{job_id}/subtitles.vtt")
async def get_job_vtt(job_id: str, lang: str = ""):
    """
    Sert le contenu VTT traduit en proxy (pas de redirection).
    Évite les problèmes CORS avec les URLs Supabase.

    Paramètres :
    - lang : langue cible pour sélectionner le VTT spécifique (ex: "fr", "es")
             Si omis, utilise la clé globale __vtt_url
    """
    try:
        jid = uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(400, "job_id invalide")

    from core.pipeline.persist import get_vtt_url

    vtt_url = await get_vtt_url(job_id)
    if not vtt_url:
        async with get_conn() as conn:
            row = await conn.fetchrow(
                "SELECT processed_steps FROM jobs WHERE id=$1",
                jid,
            )
            if row:
                ps = row["processed_steps"] or {}
                if isinstance(ps, str):
                    try:
                        ps = json.loads(ps)
                    except Exception:
                        ps = {}
                # Priorité 1 : clé par langue si demandée
                vtt_url = ""
                if lang:
                    vtt_url = ps.get(f"__vtt_url_{lang}", "")
                # Priorité 2 : clé globale
                if not vtt_url:
                    vtt_url = ps.get("__vtt_url", "")

    if not vtt_url:
        raise HTTPException(404, "VTT non disponible pour ce job")

    # Proxy : télécharger depuis Supabase et servir depuis le backend
    import httpx

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        resp = await client.get(vtt_url)
        if resp.status_code != 200:
            raise HTTPException(
                502, f"Impossible de récupérer le VTT: HTTP {resp.status_code}"
            )

    from fastapi.responses import PlainTextResponse

    return PlainTextResponse(
        content=resp.text,
        media_type="text/vtt",
        headers={
            "Access-Control-Allow-Origin": "*",
            "Cache-Control": "public, max-age=3600",
        },
    )


@router.get("/{job_id}/subtitles_source.vtt")
async def get_job_vtt_source(job_id: str):
    """
    Sert le contenu VTT source (langue originale) en proxy.
    Route dédiée pour le track source, évite les problèmes CORS.
    """
    try:
        jid = uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(400, "job_id invalide")

    vtt_source_url = ""

    # 1. Chercher dans processed_steps
    async with get_conn() as conn:
        row = await conn.fetchrow(
            "SELECT processed_steps FROM jobs WHERE id=$1",
            jid,
        )
        if row:
            ps = row["processed_steps"] or {}
            if isinstance(ps, str):
                try:
                    ps = json.loads(ps)
                except Exception:
                    ps = {}
            vtt_source_url = ps.get("__vtt_source_url", "")

    # 2. Fallback via persist.py
    if not vtt_source_url:
        from core.pipeline.persist import get_vtt_urls
        urls = await get_vtt_urls(job_id)
        vtt_source_url = urls.get("vtt_source_url", "")

    if not vtt_source_url:
        raise HTTPException(404, "VTT source non disponible pour ce job")

    # Proxy : télécharger depuis Supabase et servir depuis le backend
    import httpx

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        resp = await client.get(vtt_source_url)
        if resp.status_code != 200:
            raise HTTPException(
                502, f"Impossible de récupérer le VTT source: HTTP {resp.status_code}"
            )

    from fastapi.responses import PlainTextResponse

    return PlainTextResponse(
        content=resp.text,
        media_type="text/vtt",
        headers={
            "Access-Control-Allow-Origin": "*",
            "Cache-Control": "public, max-age=3600",
        },
    )


@router.get("/{job_id}/vtt-url")
async def get_job_vtt_url(job_id: str, lang: str = ""):
    """
    Retourne les URLs des fichiers VTT (source + traduit) pour un job sans redirection.
    Utile pour le frontend qui a besoin des URLs pour <track>.

    Paramètres :
    - lang : langue cible pour sélectionner le VTT traduit spécifique (ex: "fr", "es")
             Si omis, retourne le VTT global (première langue trouvée)

    Note : retourne toujours {vtt_url, vtt_source_url} même en cas d'erreur
    (graceful degradation, pas de 500).
    """
    try:
        jid = uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(400, "job_id invalide")

    vtt_url = ""
    vtt_source_url = ""

    try:
        async with get_conn() as conn:
            row = await conn.fetchrow(
                "SELECT processed_steps FROM jobs WHERE id=$1",
                jid,
            )
        if not row:
            raise HTTPException(404, "Job introuvable")

        ps = row["processed_steps"] or {}
        if isinstance(ps, str):
            try:
                ps = json.loads(ps)
            except Exception:
                ps = {}

        # Priorité 1 : clé spécifique à la langue si demandée
        if lang:
            vtt_url = ps.get(f"__vtt_url_{lang}", "")
            vtt_source_url = ps.get(f"__vtt_source_url_{lang}", "")

        # Priorité 2 : clé globale (rétrocompatibilité et fallback)
        if not vtt_url:
            vtt_url = ps.get("__vtt_url", "")
        if not vtt_source_url:
            vtt_source_url = ps.get("__vtt_source_url", "")

        # Priorité 3 : données persistées via persist.py (processed_files)
        if not vtt_url:
            from core.pipeline.persist import get_vtt_urls

            urls = await get_vtt_urls(job_id)
            vtt_url = urls.get("vtt_url", vtt_url)
            vtt_source_url = urls.get("vtt_source_url", vtt_source_url)
    except HTTPException:
        raise  # re-raise les 400/404 explicites
    except Exception as exc:
        logger.error(
            "Erreur inattendue dans get_job_vtt_url — retour graceful fallback",
            extra={"job_id": job_id[:8], "error": f"{type(exc).__name__}: {str(exc)[:500]}"},
        )
        # Graceful degradation : retourner des chaînes vides plutôt qu'un 500

    return {"vtt_url": vtt_url or "", "vtt_source_url": vtt_source_url or ""}


@router.get("/{job_id}/transcription")
async def get_job_transcription(job_id: str, request: Request):
    """
    Retourne les segments de transcription originaux d'un job.
    Utilisé par le frontend (studio).
    """
    try:
        uid = uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid job ID")

    async with get_conn() as conn:
        segments = await conn.fetch(
            """SELECT id, original_text as text, start_time, end_time, custom_order
               FROM transcription_segments
               WHERE job_id=$1
               ORDER BY custom_order ASC, start_time ASC""",
            uid,
        )

    if not segments:
        return []

    return [
        {
            "id": str(s["id"]),
            "text": s["text"],
            "startTime": float(s["start_time"]),
            "endTime": float(s["end_time"]),
            "order": s["custom_order"],
        }
        for s in segments
    ]


@router.get("/{job_id}/translate")
async def get_job_translation(
    job_id: str,
    request: Request,
    source: str = "",
    target: str = "",
):
    """
    Retourne les segments traduits d'un job.
    Utilisé par le frontend (studio).
    """
    try:
        uid = uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid job ID")

    async with get_conn() as conn:
        segments = await conn.fetch(
            """SELECT id, translated_text as text, start_time, end_time, custom_order
               FROM transcription_segments
               WHERE job_id=$1 AND translated_text IS NOT NULL AND translated_text != ''
               ORDER BY custom_order ASC, start_time ASC""",
            uid,
        )

    if not segments:
        return {"segments": []}

    return {
        "segments": [
            {
                "id": str(s["id"]),
                "text": s["text"],
                "translation": s["text"],
                "startTime": float(s["start_time"]),
                "endTime": float(s["end_time"]),
                "order": s["custom_order"],
            }
            for s in segments
        ]
    }