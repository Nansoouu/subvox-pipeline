"""
api/jobs/status.py — Endpoints de statut, télémétrie et métriques
"""

from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse

from api.auth import get_current_user_optional
from core.db import get_conn
from core.logging_setup import get_logger
from core.pipeline.telemetry import get_step_progress, get_eta

from ._models import JobStatusResponse, STATUS_PROGRESS, STATUS_LABEL

logger = get_logger(__name__)

router = APIRouter()


@router.get("/queue-stats")
async def get_queue_stats():
    """Retourne les statistiques de la file d'attente."""
    async with get_conn() as conn:
        active = await conn.fetchval(
            "SELECT COUNT(*) FROM jobs WHERE status IN ('downloading','transcribing','translating','burning','uploading')"
        )
        queued = await conn.fetchval(
            "SELECT COUNT(*) FROM jobs WHERE status = 'queued' AND created_at > now() - interval '2 hours'"
        )
        avg_dur = await conn.fetchval(
            "SELECT COALESCE(AVG(duration_s), 0) FROM jobs WHERE status = 'done' AND updated_at > now() - interval '1 hour'"
        )
    active_count = int(active or 0)
    queued_count = int(queued or 0)
    estimated_wait_s = int(queued_count * (float(avg_dur or 90) + 30))
    return {
        "active_count": active_count,
        "queued_count": queued_count,
        "estimated_wait_s": estimated_wait_s,
    }


@router.get("/{job_id}")
async def get_job_redirect(job_id: str):
    """Redirige /jobs/{id} vers /jobs/{id}/status (pour compatibilité frontend)."""
    return RedirectResponse(url=f"/jobs/{job_id}/status", status_code=307)


@router.get("/{job_id}/status", response_model=JobStatusResponse)
async def get_job_status(job_id: str, user=Depends(get_current_user_optional)):
    try:
        jid = uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(400, "job_id invalide")
    async with get_conn() as conn:
        row = await conn.fetchrow(
            "SELECT id, user_id, status, error_msg, storage_url, storage_key, thumbnail_url, summary, summaries, step_data, source_lang, target_lang, duration_s, video_type, source_url, video_width, video_height, source_storage_url, source_sub_url, original_filename, download_only, mode, title, download_count, retry_count, job_metrics, seo_slug, seo_metadata, created_at, updated_at, archived_at FROM jobs WHERE id=$1",
            jid,
        )
    if not row:
        raise HTTPException(404, "Job introuvable")
    can_download = row["status"] == "done" and bool(row["storage_url"])
    storage_url = row["storage_url"]
    if storage_url:
        filename = storage_url.rsplit("/", 1)[-1]
        storage_url = f"/storage/{filename}"
    estimated_total_seconds = None
    estimated_burn_seconds = None
    duration_s = row["duration_s"]
    if duration_s is not None and row["status"] in [
        "transcribing",
        "translating",
        "burning",
        "uploading",
    ]:
        try:
            from core.utils import estimate_processing_time

            estimates = estimate_processing_time(duration_s)
            estimated_total_seconds = estimates["estimated_total_seconds"]
            estimated_burn_seconds = estimates["estimated_burn_seconds"]
        except Exception:
            pass
    # Calcul de la position dans la file
    queue_position = None
    estimated_start_in_s = None
    if row["status"] in ("queued", "downloading", "transcribing", "translating"):
        async with get_conn() as conn:
            if row["status"] == "queued":
                # Jobs 'queued' crees avant ce job
                ahead = await conn.fetchrow(
                    """
                    SELECT COUNT(*) AS cnt, COALESCE(SUM(duration_s), 0) AS dur
                    FROM jobs
                    WHERE status = 'queued'
                      AND created_at > now() - interval '2 hours'
                      AND created_at < (SELECT created_at FROM jobs WHERE id=$1)
                    """,
                    jid,
                )
                cnt_ahead = int(ahead["cnt"] or 0)
                dur_ahead = float(ahead["dur"] or 0)
                queue_position = cnt_ahead + 1  # position 1-based
                estimated_start_in_s = cnt_ahead * 90 + dur_ahead * 1.3
            else:
                # En cours de traitement: position = 0 (en train d'etre traite)
                queue_position = 0
                estimated_start_in_s = 0
    # ── Parser summaries JSONB (asyncpg peut retourner str ou dict) ─
    raw_summaries = row["summaries"]
    parsed_summaries: dict | None = None
    if raw_summaries is not None:
        if isinstance(raw_summaries, dict):
            parsed_summaries = raw_summaries
        elif isinstance(raw_summaries, str):
            try:
                parsed_summaries = json.loads(raw_summaries)
            except (json.JSONDecodeError, TypeError):
                parsed_summaries = None
    # Parser seo_metadata JSONB (asyncpg peut retourner str ou dict)
    raw_seo_metadata = row.get("seo_metadata")
    parsed_seo_metadata: dict | None = None
    if raw_seo_metadata is not None:
        if isinstance(raw_seo_metadata, dict):
            parsed_seo_metadata = raw_seo_metadata
        elif isinstance(raw_seo_metadata, str):
            try:
                parsed_seo_metadata = json.loads(raw_seo_metadata)
            except (json.JSONDecodeError, TypeError):
                parsed_seo_metadata = None

    # Parser job_metrics JSONB (asyncpg peut retourner str ou dict)
    raw_job_metrics = row["job_metrics"]
    parsed_job_metrics: dict | None = None
    if raw_job_metrics is not None:
        if isinstance(raw_job_metrics, dict):
            parsed_job_metrics = raw_job_metrics
        elif isinstance(raw_job_metrics, str):
            try:
                parsed_job_metrics = json.loads(raw_job_metrics)
            except (json.JSONDecodeError, TypeError):
                parsed_job_metrics = None
    # Formater les dates ISO
    created_at = row["created_at"].isoformat() if row["created_at"] else None
    updated_at = row["updated_at"].isoformat() if row["updated_at"] else None
    archived_at = row["archived_at"].isoformat() if row["archived_at"] else None
    user_id_str = str(row["user_id"]) if row["user_id"] else None

    # ── Récupérer les URLs VTT depuis processed_steps ─────────────────
    vtt_url = None
    vtt_source_url = None
    if row["status"] == "done":
        try:
            from core.pipeline.persist import get_vtt_urls

            urls = await get_vtt_urls(job_id)
            vtt_url = urls.get("vtt_url") or None
            vtt_source_url = urls.get("vtt_source_url") or None
            if not vtt_url:
                # Fallback ancienne clé
                async with get_conn() as conn2:
                    ps_row = await conn2.fetchrow(
                        "SELECT processed_steps FROM jobs WHERE id=$1", jid
                    )
                    if ps_row:
                        ps = ps_row["processed_steps"] or {}
                        if isinstance(ps, str):
                            import json as _json

                            try:
                                ps = _json.loads(ps)
                            except Exception:
                                ps = {}
                        vtt_url = ps.get("__vtt_url") or vtt_url
                        vtt_source_url = ps.get("__vtt_source_url") or vtt_source_url
        except Exception:
            pass

    # Convertir les URLs file:// en /storage/ pour le frontend
    raw_source_storage_url = row["source_storage_url"]
    source_storage_url = raw_source_storage_url
    if source_storage_url and source_storage_url.startswith("file://"):
        filename = source_storage_url.rsplit("/", 1)[-1]
        source_storage_url = f"/storage/{filename}"

    # ── Extraire burned_languages de step_data ──────────────────────────
    burned_languages = None
    raw_step_data = row.get("step_data")
    if isinstance(raw_step_data, dict):
        burned_languages = raw_step_data.get("burned_languages")
    elif isinstance(raw_step_data, str):
        try:
            import json as _json
            burned_languages = _json.loads(raw_step_data).get("burned_languages")
        except Exception:
            pass

    return JobStatusResponse(
        vtt_url=vtt_url,
        vtt_source_url=vtt_source_url,
        job_id=str(row["id"]),
        seo_slug=row.get("seo_slug") or None,
        seo_metadata=parsed_seo_metadata,
        status=row["status"],
        progress_pct=STATUS_PROGRESS.get(row["status"], 0),
        status_label=STATUS_LABEL.get(row["status"], row["status"]),
        error_msg=row["error_msg"],
        storage_url=storage_url,
        storage_key=row["storage_key"] or None,
        thumbnail_url=row["thumbnail_url"] or None,
        summary=row["summary"],
        summaries=parsed_summaries,
        source_lang=row["source_lang"],
        target_lang=row["target_lang"],
        duration_s=duration_s,
        video_type=row["video_type"],
        can_download=can_download,
        is_public=True,
        estimated_total_seconds=estimated_total_seconds,
        estimated_burn_seconds=estimated_burn_seconds,
        queue_position=queue_position,
        estimated_start_in_s=estimated_start_in_s,
        source_url=row["source_url"],
        video_width=row.get("video_width"),
        video_height=row.get("video_height"),
        source_storage_url=source_storage_url,
        source_sub_url=row.get("source_sub_url") or None,
        original_filename=row["original_filename"],
        download_only=row["download_only"],
        mode=row["mode"],
        title=row["title"],
        user_id=user_id_str,
        download_count=row["download_count"],
        retry_count=row["retry_count"],
        job_metrics=parsed_job_metrics,
        burned_languages=burned_languages,
        created_at=created_at,
        updated_at=updated_at,
        archived_at=archived_at,
    )


@router.get("/{job_id}/telemetry")
async def get_job_telemetry(job_id: str):
    """
    Retourne les données de télémétrie enrichies du pipeline.
    Combine les colonnes JSONB de la DB + Redis (step_progress, eta).
    """
    try:
        jid = uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(400, "job_id invalide")
    async with get_conn() as conn:
        row = await conn.fetchrow(
            """SELECT step_timings, step_data, source_info, subtitle_info,
                      cost_breakdown, processing_log, video_category
               FROM jobs WHERE id=$1""",
            jid,
        )
    if not row:
        raise HTTPException(404, "Job introuvable")

    # Lire Redis pour les données live
    live_step_progress = await get_step_progress(job_id)
    live_eta = await get_eta(job_id)

    return {
        "step_timings": row["step_timings"] or {},
        "step_data": row["step_data"] or {},
        "source_info": row["source_info"] or {},
        "subtitle_info": row["subtitle_info"] or {},
        "cost_breakdown": row["cost_breakdown"] or {},
        "processing_log": row["processing_log"] or [],
        "video_category": row["video_category"] or "short",
        "live_step_progress": live_step_progress,
        "live_eta": live_eta,
    }


@router.get("/{job_id}/metrics")
async def get_job_metrics(job_id: str):
    """Retourne les métriques structurées du pipeline (job_metrics JSONB)."""
    try:
        jid = uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(400, "job_id invalide")
    async with get_conn() as conn:
        row = await conn.fetchrow("SELECT job_metrics FROM jobs WHERE id=$1", jid)
    if not row:
        raise HTTPException(404, "Job introuvable")
    return row["job_metrics"] or {}