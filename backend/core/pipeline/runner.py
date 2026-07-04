"""
pipeline/runner.py — Orchestrateur du pipeline optimisé — Subvox

Optimisations 2026-05-08 :
  1. Summary avancé juste après filtering (gain -66% temps avant résumé visible)
  2. Phase 3 parallélisée : meta_analysis + text_analysis + visual_analysis en asyncio.gather()
  3. visual_analysis enrichi par les timestamps SRT (frames ciblées)
  4. SEO déplacé en arrière-plan non-bloquant après la traduction
  5. watermark + burn + upload en Phase 6 (non-bloquant si soft_subs)
"""

from __future__ import annotations

import json
from pathlib import Path

import asyncio
from datetime import datetime, timezone
import httpx
from core.config import settings
from core.logging_setup import get_logger
from core.pipeline.metrics import get_collector
from core.pipeline.telemetry import TelemetryWriter
from core.pipeline.eta import compute_video_category
from core.pipeline.persist import (
    get_completed_steps,
    mark_step_completed,
    save_step_data,
    save_pipeline_file,
    load_step_data,
    get_summary_for_lang,
    save_filtered_srt,
    set_error_context,
    increment_resume_attempts,
    STEPS_ORDERED,
    get_vtt_url,
)
from core.pipeline.seo import generate_seo_all_langs, save_seo_metadata_multilingual
from core.pipeline.duration_tiers import get_tier, DurationTier
from core.pipeline.steps import (
    StepResult,
    step_download,
    step_transcribe,
    step_filter,
    step_summary,
    step_translate,
    step_segments_save,
    step_ass_generation,
    step_vtt_export,
    step_watermark,
    step_burn,
    step_upload,
    step_meta_analysis,
    step_text_analysis,
    step_visual_analysis,
    step_anonymization,
    step_speaker_analysis,
    step_fusion,
    _get_tmp,
)
from core.pipeline._runner_helpers import (
    _set_status,
    _update_progress,
    _start_heartbeat,
    _stop_heartbeat,
    _find_source_job,
    _copy_source_job_data,
    _ensure_source_mp4,
    _finalize_pipeline,
)

logger = get_logger(__name__)

BURN_UPLOAD_MAX_RETRIES: int = 3
BURN_UPLOAD_RETRY_DELAY_S: float = 5.0


async def _retry_burn_upload(
    job_id: str,
    step_name: str,
    log_extra: dict,
    fn,
    *args,
    **kwargs,
) -> StepResult:
    """Retry un step burn/upload jusqu'à BURN_UPLOAD_MAX_RETRIES fois."""
    last_error: str = ""
    for attempt in range(1, BURN_UPLOAD_MAX_RETRIES + 1):
        try:
            result = await fn(*args, **kwargs)
            if result.success:
                return result
            last_error = result.error or "erreur inconnue"
        except Exception as exc:
            last_error = str(exc)
        if attempt < BURN_UPLOAD_MAX_RETRIES:
            logger.warning(
                f"Retry {attempt}/{BURN_UPLOAD_MAX_RETRIES} pour '{step_name}' dans {BURN_UPLOAD_RETRY_DELAY_S}s",
                extra={"error": last_error, **log_extra},
            )
            await asyncio.sleep(BURN_UPLOAD_RETRY_DELAY_S)
    return StepResult(
        success=False,
        error=f"Etape {step_name} echouee apres {BURN_UPLOAD_MAX_RETRIES} tentatives: {last_error}",
    )


# ─── Helper : parallélisation des analyses ─────────────────────────────────


async def _run_analysis_parallel(
    job_id: str,
    tmp: Path,
    completed: set[str],
    dl_data: dict,
    tx_data: dict,
    srt_timestamps: list[float] | None = None,
) -> dict[str, dict]:
    """
    Exécute meta_analysis + text_analysis + visual_analysis EN PARALLÈLE
    via asyncio.gather().

    Retourne un dict {step_name: data} pour chaque étape complétée.
    """
    log_extra = {"job_id": job_id[:8]}
    results: dict[str, dict] = {}

    async def _do_meta() -> dict:
        """Analyse des métadonnées (titre/description)."""
        nonlocal results
        result = await step_meta_analysis(
            job_id,
            video_title=dl_data.get("video_title", ""),
            video_description=dl_data.get("video_description", ""),
            duration_s=float(dl_data.get("duration_s", 0)),
        )
        if result.success and result.data:
            await save_step_data(job_id, "meta_analysis", result.data)
            category = result.data.get("category", "")
            if category:
                try:
                    from uuid import UUID
                    from core.db import direct_connect as _direct
                    async with _direct() as conn:
                        await conn.execute(
                            "UPDATE jobs SET category=$1, updated_at=now() WHERE id=$2",
                            category[:50], UUID(job_id),
                        )
                except Exception:
                    pass
        await mark_step_completed(job_id, "meta_analysis")
        return result.data or {}

    async def _do_text() -> dict:
        """Analyse textuelle (via transcript)."""
        nonlocal results
        transcript = tx_data.get("raw_srt", "") or tx_data.get("text", "")
        result = await step_text_analysis(
            job_id, transcript=transcript,
            title=dl_data.get("video_title", ""),
            description=dl_data.get("video_description", ""),
        )
        if result.success and result.data:
            await save_step_data(job_id, "text_analysis", result.data)
        await mark_step_completed(job_id, "text_analysis")
        return result.data or {}

    async def _do_visual() -> dict:
        """Analyse visuelle (frames vidéo)."""
        nonlocal results
        source_mp4_path = tmp / "source.mp4"
        dur_s = float(dl_data.get("duration_s", 0))
        await _ensure_source_mp4(job_id, tmp, dl_data.get("source_storage_url"))
        if source_mp4_path.exists() and dur_s > 0:
            result = await step_visual_analysis(
                job_id,
                video_path=str(source_mp4_path),
                duration_s=dur_s,
                srt_timestamps=srt_timestamps,  # ← enrichi par timestamps SRT
            )
            if result.success and result.data:
                await save_step_data(job_id, "visual_analysis", result.data)
                await mark_step_completed(job_id, "visual_analysis")
                return result.data
        logger.warning("Visual-analysis skip: source.mp4 absent ou durée nulle", extra=log_extra)
        await mark_step_completed(job_id, "visual_analysis")
        return {"scene_count": 0, "scenes": [], "global_faces_count": 0}

    # Lancer les 3 analyses en parallèle
    meta_task = asyncio.create_task(_do_meta())
    text_task = asyncio.create_task(_do_text())
    visual_task = asyncio.create_task(_do_visual())

    meta_result, text_result, visual_result = await asyncio.gather(
        meta_task, text_task, visual_task, return_exceptions=True,
    )

    # Gérer les erreurs individuelles
    for name, res in [("meta_analysis", meta_result), ("text_analysis", text_result), ("visual_analysis", visual_result)]:
        if isinstance(res, Exception):
            logger.error(f"Analyse {name} echouee", extra={"error": str(res), **log_extra})
            results[name] = {}
        else:
            results[name] = res

    return results


async def run_pipeline(
    job_id: str,
    source_url: str,
    target_lang: str = "fr",
    user_id: str = "anonymous",
    download_only: bool = False,
    original_filename: str | None = None,
    cookies_file: str = "",
    groq_api_key: str = "",
    _source_job_id: str = "",
    soft_subs: bool = True,
) -> dict:
    """
    Pipeline principal -- version optimisée (2026-05-08).

    Nouvel ordre d'exécution :
      Phase 1 : downloading
      Phase 2 : transcribing → filtering → summary (résumé rapide)
      Phase 3 : meta_analysis + text_analysis + visual_analysis EN PARALLÈLE
      Phase 4 : anonymization → speaker_analysis → fusion
      Phase 5 : translating → segments_save → ass_generation → vtt_export
      Phase 6 : seo (non-bloquant) → watermark → burn → upload
    """
    from core.db import direct_connect as _direct
    from uuid import UUID

    import time as _time

    log_extra = {"job_id": job_id, "user_id": user_id}
    duration = 0.0
    source_lang = ""
    summary = ""
    storage_key = ""
    _db_update_ok = False
    thumbnail_url = None
    source_storage_url = None
    video_type = "long"
    vtt_storage_url = ""
    vtt_source_storage_url = ""
    video_width = 0
    video_height = 0
    duration_tier: DurationTier | None = None

    # ── Initialiser le collecteur de métriques et la télémétrie ─────────
    metrics = get_collector(job_id)
    metrics.set_meta(source_url=source_url, target_lang=target_lang)
    _step_start: dict[str, float] = {}
    telemetry = TelemetryWriter(job_id)

    await telemetry.append_processing_log(
        "pipeline_start",
        "init",
        f"Pipeline demarre (optimise): source={source_url[:50]} lang={target_lang} soft_subs={soft_subs}",
    )

    # ── Déterminer si reprise ──────────────────────────────────────────────
    completed = await get_completed_steps(job_id)
    is_resume = len(completed) > 0
    if is_resume:
        attempts = await increment_resume_attempts(job_id)
        if attempts > 10:
            error_msg = f"Trop de tentatives de reprise ({attempts}) -- abandon"
            logger.error(error_msg, extra=log_extra)
            raise RuntimeError(error_msg)
        logger.info(
            f"Reprise detectee -- {len(completed)}/{len(STEPS_ORDERED)} etapes deja faites "
            f"(tentative {attempts}/3)",
            extra=log_extra,
        )

    log_extra["resume"] = is_resume
    log_extra["completed_before"] = list(completed)

    # ── Mission 6 : Détection auto de job source ──────────────────────────
    if not _source_job_id and "downloading" not in completed:
        _source_job_id = await _find_source_job(source_url)

    logger.info(
        f"Pipeline start: mode={'download' if download_only else 'translate'} "
        f"target={target_lang} soft_subs={soft_subs} {'(resume)' if is_resume else ''}",
        extra=log_extra,
    )

    tmp = _get_tmp(job_id)
    tmp.mkdir(parents=True, exist_ok=True)

    try:
        # ═══════════════════════════════════════════════════════════════════
        # PHASE 1 — Acquisition
        # ═══════════════════════════════════════════════════════════════════
        if _source_job_id and "downloading" not in completed:
            try:
                _dur, _sl, _tn, _vt, _ssu = await _copy_source_job_data(
                    job_id, _source_job_id, tmp, completed
                )
                duration = _dur
                source_lang = _sl
                thumbnail_url = _tn
                video_type = _vt
                source_storage_url = _ssu
            except Exception:
                logger.warning(
                    "Copie depuis _source_job_id échouée — fallback pipeline normal",
                    extra={"job_id": job_id[:8]},
                )
                completed.discard("downloading")
                completed.discard("transcribing")
                completed.discard("filtering")

        if "downloading" not in completed:
            await _set_status(job_id, "downloading")
            _step_start["downloading"] = _time.time()
            result = await step_download(
                job_id, source_url, cookies_file, download_only
            )
            metrics.record_step(
                "downloading", duration_s=_time.time() - _step_start["downloading"]
            )
            if not result.success:
                raise RuntimeError(f"Etape download echouee: {result.error}")

            if download_only:
                return result.data

            await save_step_data(job_id, "downloading", result.data)
            if "source_mp4" in result.files:
                await save_pipeline_file(
                    job_id, "downloading", "source_mp4", result.files["source_mp4"]
                )
            await mark_step_completed(job_id, "downloading")

            duration = float(result.data.get("duration_s", 0))
            source_lang = result.data.get("source_lang", "")
            thumbnail_url = result.data.get("thumbnail_url")
            video_type = result.data.get("video_type", "long")
            source_storage_url = result.data.get("source_storage_url")
            duration_tier = get_tier(duration)
            video_width = int(result.data.get("width", 0))
            video_height = int(result.data.get("height", 0))

            _step_dur = _time.time() - _step_start["downloading"]
            await telemetry.update_step_timing("downloading", status="completed", duration_s=_step_dur)
            await telemetry.update_step_data("downloading", {
                "duration_s": duration, "source_lang": source_lang,
                "video_type": video_type, "video_category": result.data.get("video_category", "short"),
                "width": video_width, "height": video_height,
                "file_size_mb": result.data.get("file_size_mb", 0),
                "frame_rate": result.data.get("frame_rate", 0),
            })
            await telemetry.update_source_info({
                "duration_s": duration, "source_lang": source_lang,
                "width": video_width, "height": video_height,
                "file_size_mb": result.data.get("file_size_mb", 0),
                "format": result.data.get("format", "mp4"),
                "video_title": result.data.get("video_title", ""),
            })
            cat = result.data.get("video_category", compute_video_category(duration))
            await telemetry.update_video_category(cat)

            metrics.set_meta(source_url=source_url, source_lang=source_lang, target_lang=target_lang)
            source_mp4_path = result.files.get("source_mp4", "")
            if source_mp4_path:
                metrics.set_video_metrics(source_mp4_path)
        else:
            logger.info("Etape 'downloading' deja completee -- skip", extra=log_extra)
            dl_data = await load_step_data(job_id, "downloading")
            if dl_data:
                duration = float(dl_data.get("duration_s", 0))
                source_lang = dl_data.get("source_lang", "")
                thumbnail_url = dl_data.get("thumbnail_url")
                video_type = dl_data.get("video_type", "long")
                source_storage_url = dl_data.get("source_storage_url")
                duration_tier = get_tier(duration)
                metrics.set_meta(source_url=source_url, source_lang=source_lang, target_lang=target_lang)

                source_mp4_path = tmp / "source.mp4"
                if not source_mp4_path.exists() and source_storage_url:
                    logger.info("source.mp4 absent — re-téléchargement depuis Supabase", extra=log_extra)
                    try:
                        async with httpx.AsyncClient(timeout=300.0) as client:
                            resp = await client.get(source_storage_url)
                            if resp.status_code == 200:
                                source_mp4_path.write_bytes(resp.content)
                            else:
                                raise RuntimeError(f"HTTP {resp.status_code}")
                    except Exception:
                        logger.warning("Re-téléchargement source.mp4 échoué — re-download forcé", extra=log_extra)
                        if source_mp4_path.exists():
                            source_mp4_path.unlink()
                        completed.discard("downloading")
                        completed.discard("transcribing")
                        completed.discard("filtering")
                elif not source_mp4_path.exists() and not source_storage_url:
                    logger.warning("source.mp4 absent et pas de source_storage_url — re-download forcé", extra=log_extra)
                    completed.discard("downloading")
                    completed.discard("transcribing")
                    completed.discard("filtering")

        # ═══════════════════════════════════════════════════════════════════
        # PHASE 2 — Transcription + Résumé rapide
        # ═══════════════════════════════════════════════════════════════════

        # ÉTAPE : Transcription Groq
        if "transcribing" not in completed:
            await _set_status(job_id, "transcribing")
            await _start_heartbeat(job_id)
            _step_start["transcribing"] = _time.time()
            result = await step_transcribe(job_id, groq_api_key)
            metrics.record_step("transcribing", duration_s=_time.time() - _step_start["transcribing"])
            await _stop_heartbeat(job_id)
            if not result.success:
                raise RuntimeError(f"Etape transcription echouee: {result.error}")

            await save_step_data(job_id, "transcribing", result.data)
            if "srt_path" in result.files:
                await save_pipeline_file(job_id, "transcribing", "srt_path", result.files["srt_path"])
            # ✨ Persist raw_srt en colonne directe pour la page watch
            if result.data.get("raw_srt"):
                from core.db import direct_connect as _direct
                from uuid import UUID
                async with _direct() as conn:
                    await conn.execute(
                        "UPDATE jobs SET raw_srt=$1, updated_at=now() WHERE id=$2 AND raw_srt IS NULL",
                        result.data["raw_srt"], UUID(job_id),
                    )
            await mark_step_completed(job_id, "transcribing")
            source_lang = result.data.get("source_lang", source_lang or "en")
        else:
            logger.info("Etape 'transcribing' deja completee -- skip", extra=log_extra)

        # ÉTAPE : Filtre hallucinations
        if "filtering" not in completed:
            tx_data = await load_step_data(job_id, "transcribing") or {}
            _step_start["filtering"] = _time.time()
            result = await step_filter(
                job_id,
                tx_data.get("raw_srt", ""),
                tx_data.get("text", ""),
                segments_json=tx_data.get("segments"),
            )
            metrics.record_step("filtering", duration_s=_time.time() - _step_start["filtering"])
            if not result.success:
                raise RuntimeError(f"Etape filter echouee: {result.error}")
            await save_step_data(job_id, "filtering", result.data)
            # ✨ Persist filtered raw_srt en colonne directe (écrase si meilleur)
            filtered_raw = result.data.get("raw_srt", "")
            if filtered_raw:
                from core.db import direct_connect as _direct
                from uuid import UUID
                async with _direct() as conn:
                    await conn.execute(
                        "UPDATE jobs SET raw_srt=$1, updated_at=now() WHERE id=$2",
                        filtered_raw, UUID(job_id),
                    )
            await mark_step_completed(job_id, "filtering")
            filtered_srt = filtered_raw
            if filtered_srt and source_lang:
                await save_filtered_srt(job_id, filtered_srt, source_lang)
        else:
            logger.info("Etape 'filtering' deja completee -- skip", extra=log_extra)

        # ÉTAPE : Résumé LLM (AVANCÉ — dispo dès que le transcript est propre)
        if "summary" not in completed:
            tx_data = await load_step_data(job_id, "transcribing") or {}
            dl_data = await load_step_data(job_id, "downloading") or {}
            transcript = tx_data.get("raw_srt", "") or tx_data.get("text", "")
            _step_start["summary"] = _time.time()
            result = await step_summary(
                job_id, transcript, source_lang,
                target_lang=target_lang,
                video_title=dl_data.get("video_title", ""),
                video_description=dl_data.get("video_description", ""),
                duration_tier=duration_tier,
            )
            metrics.record_step("summary", duration_s=_time.time() - _step_start["summary"])
            if result.success:
                summary = result.data.get("summary", "")
            await mark_step_completed(job_id, "summary")
            logger.info(
                "Resume disponible (optimise)",
                extra={"job_id": job_id[:8], "summary_len": len(summary)},
            )
        else:
            logger.info("Etape 'summary' deja completee -- skip", extra=log_extra)
            if source_lang:
                summary = await get_summary_for_lang(job_id, source_lang) or ""

        # ═══════════════════════════════════════════════════════════════════
        # PHASE 3 — Analyse enrichie (PARALLÈLE)
        # ═══════════════════════════════════════════════════════════════════

        # Extraire les timestamps SRT pour enrichir visual_analysis
        srt_timestamps: list[float] | None = None
        if "text_analysis" not in completed or "visual_analysis" not in completed or "meta_analysis" not in completed:
            tx_data = await load_step_data(job_id, "transcribing") or {}
            dl_data = await load_step_data(job_id, "downloading") or {}
            raw_srt = tx_data.get("raw_srt", "")
            if raw_srt:
                # Extraire les timestamps du SRT
                import re
                srt_timestamps = []
                for match in re.finditer(r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})", raw_srt):
                    h, m, s, ms = int(match.group(1)), int(match.group(2)), int(match.group(3)), int(match.group(4))
                    srt_timestamps.append(h * 3600 + m * 60 + s + ms / 1000)
                logger.info(
                    "SRT timestamps extraits pour visual_analysis",
                    extra={"job_id": job_id[:8], "count": len(srt_timestamps)},
                )

            # Lancer meta_analysis, text_analysis, visual_analysis EN PARALLÈLE
            _step_start["analysis_parallel"] = _time.time()
            await _run_analysis_parallel(
                job_id, tmp, completed, dl_data, tx_data,
                srt_timestamps=srt_timestamps,
            )
            elapsed = _time.time() - _step_start["analysis_parallel"]
            for name in ("meta_analysis", "text_analysis", "visual_analysis"):
                metrics.record_step(name, duration_s=elapsed / 3)
        else:
            logger.info("Analyses (Phase 3) deja completees -- skip", extra=log_extra)

        # ═══════════════════════════════════════════════════════════════════
        # PHASE 4 — Post-traitement des analyses
        # ═══════════════════════════════════════════════════════════════════

        # ÉTAPE : Anonymisation
        if "anonymization" not in completed:
            source_mp4_path = tmp / "source.mp4"
            dl_data = await load_step_data(job_id, "downloading") or {}
            dur_s = float(dl_data.get("duration_s", 0))
            meta_data = await load_step_data(job_id, "meta_analysis") or {}
            anon_config = meta_data.get("recommended_anonymization")
            await _ensure_source_mp4(job_id, tmp, dl_data.get("source_storage_url"))

            if source_mp4_path.exists() and dur_s > 0 and settings.ANONYMIZE_ENABLED:
                _step_start["anonymization"] = _time.time()
                result = await step_anonymization(job_id, video_path=str(source_mp4_path),
                                                   anonymization_config=anon_config, duration_s=dur_s)
                metrics.record_step("anonymization", duration_s=_time.time() - _step_start["anonymization"])
                if result.success and result.data:
                    await save_step_data(job_id, "anonymization", result.data)
            else:
                await save_step_data(job_id, "anonymization", {"mode": "disabled"})
            await mark_step_completed(job_id, "anonymization")
        else:
            logger.info("Etape 'anonymization' deja completee -- skip", extra=log_extra)

        # ÉTAPE : Analyse des locuteurs
        if "speaker_analysis" not in completed:
            source_mp4_path = tmp / "source.mp4"
            dl_data = await load_step_data(job_id, "downloading") or {}
            dur_s = float(dl_data.get("duration_s", 0))
            await _ensure_source_mp4(job_id, tmp, dl_data.get("source_storage_url"))
            if source_mp4_path.exists() and dur_s > 0:
                _step_start["speaker_analysis"] = _time.time()
                result = await step_speaker_analysis(job_id, video_path=str(source_mp4_path), duration_s=dur_s)
                metrics.record_step("speaker_analysis", duration_s=_time.time() - _step_start["speaker_analysis"])
                if result.success and result.data:
                    await save_step_data(job_id, "speaker_analysis", result.data)
            else:
                await save_step_data(job_id, "speaker_analysis", {"speakers": [], "total_speakers": 0})
            await mark_step_completed(job_id, "speaker_analysis")
        else:
            logger.info("Etape 'speaker_analysis' deja completee -- skip", extra=log_extra)

        # ÉTAPE : Fusion des analyses
        if "fusion" not in completed:
            _step_start["fusion"] = _time.time()
            result = await step_fusion(
                job_id,
                meta_analysis=await load_step_data(job_id, "meta_analysis"),
                text_analysis=await load_step_data(job_id, "text_analysis"),
                visual_analysis=await load_step_data(job_id, "visual_analysis"),
                anonymization=await load_step_data(job_id, "anonymization"),
                speakers=await load_step_data(job_id, "speaker_analysis"),
            )
            if result.success and result.data:
                await save_step_data(job_id, "fusion", result.data)
                try:
                    async with _direct() as conn:
                        tags = result.data.get("tags", [])[:20]
                        if tags:
                            await conn.execute(
                                "UPDATE jobs SET visual_tags=$1, updated_at=now() WHERE id=$2",
                                tags, UUID(job_id),
                            )
                        score = result.data.get("quality_score", 0)
                        if score > 0:
                            existing = await conn.fetchrow(
                                "SELECT job_metrics FROM jobs WHERE id=$1", UUID(job_id),
                            )
                            if existing:
                                jm = existing["job_metrics"] or {}
                                if isinstance(jm, str):
                                    try:
                                        jm = json.loads(jm)
                                    except Exception:
                                        jm = {}
                                jm["quality_score"] = score
                                jm["fusion_tags_count"] = len(tags) if tags else 0
                                jm["fusion_completed_at"] = datetime.now(timezone.utc).isoformat()
                                await conn.execute(
                                    "UPDATE jobs SET job_metrics=$1, updated_at=now() WHERE id=$2",
                                    json.dumps(jm), UUID(job_id),
                                )
                except Exception:
                    pass
            await mark_step_completed(job_id, "fusion")
        else:
            logger.info("Etape 'fusion' deja completee -- skip", extra=log_extra)

        # ═══════════════════════════════════════════════════════════════════
        # PHASE 5 — Traduction
        # ═══════════════════════════════════════════════════════════════════

        # ÉTAPE : Traduction SRT
        if "translating" not in completed:
            await _set_status(job_id, "translating")
            filter_data = await load_step_data(job_id, "filtering") or {}
            clean_srt = filter_data.get("raw_srt", "")
            if not clean_srt:
                tx_data = await load_step_data(job_id, "transcribing") or {}
                clean_srt = tx_data.get("raw_srt", "")
            result = await step_translate(job_id, clean_srt, source_lang, target_lang, duration_tier=duration_tier)
            if not result.success:
                raise RuntimeError(f"Etape translate echouee: {result.error}")
            await save_step_data(job_id, "translating", result.data)
            await mark_step_completed(job_id, "translating", extra_data={
                "srt_to_burn": result.data.get("srt_to_burn", ""),
                "translated_srt": result.data.get("translated_srt", ""),
            })
        else:
            logger.info("Etape 'translating' deja completee -- skip", extra=log_extra)

        # ÉTAPE : Sauvegarde segments
        if "segments_save" not in completed:
            tx_data = await load_step_data(job_id, "transcribing") or {}
            trans_data = await load_step_data(job_id, "translating") or {}
            await step_segments_save(job_id, tx_data.get("raw_srt", ""), trans_data.get("srt_to_burn", ""))
            await mark_step_completed(job_id, "segments_save")
        else:
            logger.info("Etape 'segments_save' deja completee -- skip", extra=log_extra)

        # ÉTAPE : Génération ASS
        if "ass_generation" not in completed:
            filter_data = await load_step_data(job_id, "filtering") or {}
            tx_data = await load_step_data(job_id, "transcribing") or {}
            trans_data = await load_step_data(job_id, "translating") or {}

            # SRT source (langue d'origine) pour générer un 2e ASS
            raw_srt = filter_data.get("raw_srt", "") or tx_data.get("raw_srt", "")
            if not raw_srt:
                try:
                    async with _direct() as conn:
                        row = await conn.fetchrow("SELECT raw_srt FROM jobs WHERE id=$1", UUID(job_id))
                        if row:
                            raw_srt = row["raw_srt"] or ""
                except Exception:
                    pass

            result = await step_ass_generation(
                job_id,
                trans_data.get("srt_to_burn", ""),
                source_srt=raw_srt,
                duration_tier=duration_tier,
            )
            if not result.success:
                raise RuntimeError(f"Etape ASS echouee: {result.error}")
            if "ass_path" in result.files:
                await save_pipeline_file(job_id, "ass_generation", "ass_path", result.files["ass_path"])
            if "source_ass_path" in result.files:
                await save_pipeline_file(job_id, "ass_generation", "source_ass_path", result.files["source_ass_path"])
            metrics.set_subtitle_metrics(
                total_lines=result.data.get("total_lines", 0),
                font_size=result.data.get("font_size", 14),
                ass_path=result.files.get("ass_path", ""),
                mode=result.data.get("mode", "ass"),
            )
            await mark_step_completed(job_id, "ass_generation")
        else:
            logger.info("Etape 'ass_generation' deja completee -- skip", extra=log_extra)

        # ÉTAPE : Export VTT
        if "vtt_export" not in completed:
            filter_data = await load_step_data(job_id, "filtering") or {}
            tx_data = await load_step_data(job_id, "transcribing") or {}
            _raw_srt = filter_data.get("raw_srt", "") or tx_data.get("raw_srt", "")
            if not _raw_srt:
                async with _direct() as conn:
                    row = await conn.fetchrow("SELECT raw_srt FROM jobs WHERE id=$1", UUID(job_id))
                    if row:
                        _raw_srt = row["raw_srt"] or ""

            result = await step_vtt_export(job_id, raw_srt=_raw_srt, target_lang=target_lang)
            if result.success and result.data.get("vtt_exported"):
                if "vtt_path" in result.files:
                    await save_pipeline_file(job_id, "vtt_export", "vtt_path", result.files["vtt_path"])
                if result.files.get("vtt_url"):
                    await save_pipeline_file(job_id, "vtt_export", "vtt_url", result.files["vtt_url"])
                    vtt_storage_url = result.files["vtt_url"]
                if result.files.get("vtt_source_url"):
                    await save_pipeline_file(job_id, "vtt_export", "vtt_source_url", result.files["vtt_source_url"])
                    vtt_source_storage_url = result.files["vtt_source_url"]
                await mark_step_completed(job_id, "vtt_export")
        elif "vtt_export" in completed:
            logger.info("Etape 'vtt_export' deja completee -- skip", extra=log_extra)
            vtt_storage_url = await get_vtt_url(job_id) or ""

        # ═══════════════════════════════════════════════════════════════════
        # PHASE 6 — Background (non-bloquant)
        # ═══════════════════════════════════════════════════════════════════

        # ÉTAPE : SEO multilingue (non-bloquant — ne raise pas d'erreur)
        if "seo" not in completed or "seo_all_langs" not in completed:
            try:
                dl_data = await load_step_data(job_id, "downloading") or {}
                fusion_data = await load_step_data(job_id, "fusion")
                skip_langs = {target_lang}
                if source_lang:
                    skip_langs.add(source_lang)

                seo_all = await generate_seo_all_langs(
                    job_id=job_id,
                    raw_title=dl_data.get("video_title", ""),
                    category=dl_data.get("video_category", ""),
                    duration_s=float(dl_data.get("duration_s", 0)),
                    summary=summary,
                    analysis_result=fusion_data if fusion_data else None,
                    source_lang=source_lang,
                    skip_langs=skip_langs,
                )
                if seo_all:
                    await save_seo_metadata_multilingual(job_id, seo_all)
                await mark_step_completed(job_id, "seo")
            except Exception as seo_err:
                logger.warning(
                    "SEO multilingue non-bloquant echoue",
                    extra={"error": str(seo_err), **log_extra},
                )
                await mark_step_completed(job_id, "seo")
        else:
            if "seo" in completed or "seo_all_langs" in completed:
                logger.info("Etape SEO deja completee -- skip", extra=log_extra)

        # ÉTAPE : Watermark PNG
        if "watermark" not in completed:
            result = await step_watermark(job_id, user_id)
            wm_data = dict(result.data)
            wm_data["encoding_time_s"] = _time.time() - _step_start.get("watermark", _time.time())
            await save_step_data(job_id, "watermark", wm_data)
            if result.data.get("watermark_generated") and "watermark_png" in result.files:
                await save_pipeline_file(job_id, "watermark", "watermark_png", result.files["watermark_png"])
            await mark_step_completed(job_id, "watermark")
        else:
            logger.info("Etape 'watermark' deja completee -- skip", extra=log_extra)

        # ═══════════════════════════════════════════════════════════════════
        # Burn + Upload (3 vidéos : brute, sous-titrée source, sous-titrée cible)
        # ═══════════════════════════════════════════════════════════════════
        source_sub_url = None  # URL de la vidéo brute + sous-titres langue source

        if soft_subs:
            logger.info("Mode soft_subs : burn différé en arrière-plan", extra=log_extra)
            if source_storage_url:
                storage_key = source_storage_url
            else:
                logger.warning("source_storage_url manquant en mode soft_subs — upload forcé", extra=log_extra)
                source_mp4_path = tmp / "source.mp4"
                if source_mp4_path.exists():
                    try:
                        from core.supabase_storage import upload_video as _upload_video
                        up_res = await _upload_video(
                            f"source_{job_id}", source_mp4_path, filename=f"source_{job_id}.mp4",
                        )
                        if up_res and up_res.get("storage_url"):
                            storage_key = up_res["storage_url"]
                            source_storage_url = storage_key
                        else:
                            storage_key = ""
                    except Exception as exc:
                        storage_key = ""
                        logger.error("Upload source de rattrapage echoue", extra={"error": str(exc), **log_extra})
                else:
                    storage_key = ""
            if "burning" not in completed:
                await mark_step_completed(job_id, "burning")
            if "uploading" not in completed:
                await mark_step_completed(job_id, "uploading")
            # Déclencher le burn asynchrone en arrière-plan après le pipeline
            try:
                from tasks.pipeline_task import burn_job_background
                burn_job_background.delay(job_id, watermark=True)
                logger.info("Tâche de burn asynchrone déclenchée", extra=log_extra)
            except Exception as burn_exc:
                logger.warning(
                    "Impossible de déclencher le burn asynchrone (Celery non disponible ?)",
                    extra={"error": str(burn_exc), **log_extra},
                )
        else:
            # ── Mode legacy : 2 burns parallèles (source + cible) ──────────
            source_ass_path = tmp / "source_subtitles.ass"
            tmp / "subtitles.ass"
            has_source_ass = source_ass_path.exists()

            async def _burn_target():
                if "burning" not in completed:
                    def _on_burn_progress(pct: int):
                        try:
                            asyncio.ensure_future(_update_progress(job_id, pct, status="burning"))
                        except Exception:
                            pass
                    return await _retry_burn_upload(
                        job_id, "burn", log_extra, step_burn, job_id,
                        on_progress=_on_burn_progress,
                        output_filename="burned_target.mp4",
                    )
                result = StepResult(success=True)
                burned_mp4 = tmp / "burned_target.mp4"
                if burned_mp4.exists():
                    result.files = {"burned_mp4": str(burned_mp4)}
                return result

            async def _burn_source():
                if not has_source_ass:
                    return StepResult(success=True, data={"skipped": True})
                if "burning" not in completed:
                    return await _retry_burn_upload(
                        job_id, "burn_source", log_extra, step_burn, job_id,
                        ass_path_override=str(source_ass_path),
                        output_filename="burned_source.mp4",
                    )
                result = StepResult(success=True)
                burned_mp4 = tmp / "burned_source.mp4"
                if burned_mp4.exists():
                    result.files = {"burned_mp4": str(burned_mp4)}
                return result

            if "burning" not in completed:
                await _set_status(job_id, "burning")
                await _start_heartbeat(job_id)

                # Lancer les 2 burns EN PARALLÈLE
                burn_tgt, burn_src = await asyncio.gather(
                    _burn_target(), _burn_source(), return_exceptions=True,
                )

                # Gérer les erreurs individuellement
                if isinstance(burn_tgt, Exception) or (isinstance(burn_tgt, StepResult) and not burn_tgt.success):
                    err = str(burn_tgt) if isinstance(burn_tgt, Exception) else (burn_tgt.error or "burn cible echoue")
                    raise RuntimeError(f"Burn cible echoue: {err}")
                if isinstance(burn_src, Exception):
                    logger.warning(f"Burn source echoue (non-bloquant): {burn_src}", extra=log_extra)
                    burn_src = StepResult(success=True, data={"skipped": True})

                await _stop_heartbeat(job_id)

                if burn_tgt and "burned_mp4" in burn_tgt.files:
                    await save_pipeline_file(job_id, "burning", "burned_mp4", burn_tgt.files["burned_mp4"])
                if isinstance(burn_src, StepResult) and burn_src.files and "burned_mp4" in burn_src.files:
                    await save_pipeline_file(job_id, "burning", "burned_source_mp4", burn_src.files["burned_mp4"])

                _burn_data = {}
                if hasattr(burn_tgt, "data"):
                    _burn_data.update(burn_tgt.data)
                _burn_data["encoding_time_s"] = _time.time() - _step_start.get("burning", _time.time())
                _burn_data["hwaccel"] = burn_tgt.data.get("hwaccel", "libx264") if hasattr(burn_tgt, "data") else "libx264"
                _burn_data["burn_ok_tgt"] = True
                _burn_data["burn_ok_src"] = isinstance(burn_src, StepResult) and burn_src.success and "burned_mp4" in (burn_src.files or {})
                await save_step_data(job_id, "burning", _burn_data)
                await mark_step_completed(job_id, "burning")
                metrics.set_burn_metrics(
                    mode=burn_tgt.data.get("burn_mode", "ass") if hasattr(burn_tgt, "data") else "ass",
                    total_frames=burn_tgt.data.get("burn_total_frames", 0) if hasattr(burn_tgt, "data") else 0,
                    duration_s=burn_tgt.data.get("burn_duration_s", 0.0) if hasattr(burn_tgt, "data") else 0.0,
                    output_size_mb=burn_tgt.data.get("burn_output_size_mb", 0.0) if hasattr(burn_tgt, "data") else 0.0,
                    fps_avg=burn_tgt.data.get("burn_fps_avg", 0.0) if hasattr(burn_tgt, "data") else 0.0,
                )
            else:
                logger.info("Etape 'burning' deja completee -- skip", extra=log_extra)

            # ── 2 uploads parallèles ──────────────────────────────────────
            async def _upload_target():
                if "uploading" not in completed:
                    return await _retry_burn_upload(
                        job_id, "upload", log_extra, step_upload, job_id,
                        source_path=str(tmp / "burned_target.mp4"),
                    )
                return StepResult(success=True, data={
                    "storage_url": storage_key or "",
                })

            async def _upload_source():
                if not has_source_ass:
                    return StepResult(success=True, data={"skipped": True})
                if "uploading" not in completed:
                    # Upload vers le prefix source_sub_
                    src_path = str(tmp / "burned_source.mp4")
                    return await _retry_burn_upload(
                        job_id, "upload_source", log_extra, step_upload, job_id,
                        source_path=src_path, prefix="source_sub_",
                    )
                return StepResult(success=True, data={"skipped": True})

            if "uploading" not in completed:
                await _set_status(job_id, "uploading")
                up_tgt, up_src = await asyncio.gather(
                    _upload_target(), _upload_source(), return_exceptions=True,
                )

                if isinstance(up_tgt, Exception) or (isinstance(up_tgt, StepResult) and not up_tgt.success):
                    err = str(up_tgt) if isinstance(up_tgt, Exception) else (up_tgt.error or "upload cible echoue")
                    raise RuntimeError(f"Upload cible echoue: {err}")

                storage_key = up_tgt.data.get("storage_url", "")

                if isinstance(up_src, StepResult) and up_src.success and up_src.data.get("storage_url"):
                    source_sub_url = up_src.data["storage_url"]
                    logger.info("Upload source subtitree OK", extra={"job_id": job_id[:8], "url": source_sub_url[:80]})

                await telemetry.update_step_data("uploading", {
                    "file_size_mb": up_tgt.data.get("file_size_mb", 0) if hasattr(up_tgt, "data") else 0,
                    "upload_filename": up_tgt.data.get("upload_filename", "") if hasattr(up_tgt, "data") else "",
                })
                await mark_step_completed(job_id, "uploading")
            else:
                logger.info("Etape 'uploading' deja completee -- skip", extra=log_extra)
                async with _direct() as conn:
                    row = await conn.fetchrow("SELECT storage_url, source_sub_url FROM jobs WHERE id=$1", UUID(job_id))
                    if row:
                        if row["storage_url"]:
                            storage_key = row["storage_url"]
                        if row["source_sub_url"]:
                            source_sub_url = row["source_sub_url"]

        # ═══════════════════════════════════════════════════════════════════
        # Finalisation
        # ═══════════════════════════════════════════════════════════════════
        result_dict = await _finalize_pipeline(
            job_id=job_id,
            storage_key=storage_key,
            summary=summary,
            source_lang=source_lang,
            duration=duration,
            video_type=video_type,
            thumbnail_url=thumbnail_url,
            source_storage_url=source_storage_url,
            video_width=video_width,
            video_height=video_height,
            vtt_storage_url=vtt_storage_url,
            vtt_source_storage_url=vtt_source_storage_url,
            target_lang=target_lang,
            soft_subs=soft_subs,
            source_sub_url=source_sub_url,
            metrics=metrics,
            log_extra=log_extra,
        )
        return result_dict

    except Exception as exc:
        logger.error(f"Pipeline echoue: {exc}", extra={"error": str(exc), **log_extra})
        await set_error_context(
            job_id, "pipeline", str(exc),
            completed_steps=list(completed),
            is_resume=is_resume,
        )
        try:
            await _set_status(job_id, "error", error_msg=str(exc)[:500])
        except Exception:
            pass
        raise


# Alias de compatibilite pour pipeline_task.py
process_video = run_pipeline