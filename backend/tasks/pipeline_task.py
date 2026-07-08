"""
tasks/pipeline_task.py - Tache Celery pipeline video - Subvox

Refactored v2 : utilise le module persist pour détecter la reprise
après crash worker. Vérifie l'état du job + les étapes déjà complétées
pour éviter de re-exécuter ce qui est déjà fait.
"""

import asyncio
import json
import os
import shutil
import uuid
from pathlib import Path
from core.celery_app import celery_app
from core.logging_setup import get_logger

logger = get_logger(__name__)


async def _check_job_status(job_id: str) -> str | None:
    """Retourne le status du job s'il est déjà done/error, sinon None."""
    from core.db import direct_connect

    try:
        async with direct_connect() as conn:
            row = await conn.fetchrow(
                "SELECT status FROM jobs WHERE id=$1",
                uuid.UUID(job_id),
            )
        if row and row["status"] in ("done", "error"):
            return row["status"]
    except Exception:
        pass
    return None


async def _check_resume_state(job_id: str) -> dict:
    """
    Vérifie l'état de reprise d'un job.
    Retourne un dict avec resume_possible, completed_steps, status.
    """
    from core.pipeline.persist import get_completed_steps
    from core.db import direct_connect

    completed = set()
    status = "unknown"

    try:
        async with direct_connect() as conn:
            row = await conn.fetchrow(
                "SELECT status FROM jobs WHERE id=$1",
                uuid.UUID(job_id),
            )
            if row:
                status = row["status"]

        completed = await get_completed_steps(job_id)
    except Exception as exc:
        logger.warning(
            "Erreur vérification état reprise",
            extra={"job_id": job_id[:8], "error": str(exc)},
        )

    return {
        "status": status,
        "completed_steps": completed,
        "resume_possible": len(completed) > 0 and status not in ("done", "error"),
    }


async def _force_done_status(
    job_id: str,
    storage_url: str,
    storage_key: str,
    source_lang,
    thumbnail_url,
    duration_s: int = 0,
) -> None:
    """Force le statut 'done' en DB apres upload reussi."""
    from core.db import direct_connect

    try:
        async with direct_connect() as conn:
            await conn.execute(
                """
                UPDATE jobs SET
                    status        = 'done',
                    storage_key   = $2,
                    storage_url   = $3,
                    source_lang   = $4,
                    thumbnail_url = $5,
                    duration_s    = $6,
                    updated_at    = now()
                WHERE id = $1
                  AND status != 'done'
                """,
                uuid.UUID(job_id),
                storage_key,
                storage_url,
                source_lang,
                thumbnail_url,
                duration_s,
            )
        logger.info(f"DB status forcé → done pour {job_id[:8]}")

        # Phase 3.2: Créditer publisher pour retraduction
        try:
            from core.pipeline._runner_helpers import _credit_retraduction_publisher
            await _credit_retraduction_publisher(job_id)
        except ImportError:
            pass
        except Exception as cred_exc:
            logger.warning(f"Retraduction credit failed in force_done: {cred_exc}")

    except Exception as e:
        logger.error(f"_force_done_status échoué: {e}")


@celery_app.task(
    name="tasks.pipeline_task.process_video_task",
    bind=True,
    max_retries=2,
    default_retry_delay=300,
    time_limit=43200,
    soft_time_limit=36000,
    queue="xlong",
)
def process_video_task(
    self,
    job_id: str,
    source_url: str,
    target_lang: str,
    user_id: str,
    download_only: bool = False,
    original_filename: str | None = None,
    _source_job_id: str | None = None,
):
    """Enveloppe Celery pour le pipeline async process_video()."""
    import core.db as _db

    from core.pipeline import process_video
    from core.config import settings

    # ── 1. Vérifier si le job est déjà terminé ───────────────────────────
    try:
        _check = asyncio.run(_check_job_status(job_id))
        if _check:
            logger.info(
                f"Job {job_id[:8]} déjà {_check} — skip",
                extra={"job_id": job_id},
            )
            return {"skipped": True, "status": _check}
    except Exception:
        pass

    # ── 2. Vérifier l'état de reprise ────────────────────────────────────
    resume_state = {}
    try:
        resume_state = asyncio.run(_check_resume_state(job_id))
        if resume_state.get("resume_possible"):
            steps = list(resume_state.get("completed_steps", set()))
            logger.info(
                f"Reprise détectée pour job {job_id[:8]} — "
                f"{len(steps)} étapes déjà complétées: {steps}",
                extra={"job_id": job_id, "resume_steps": steps},
            )
        else:
            logger.info(
                f"Nouveau job {job_id[:8]} — aucune reprise",
                extra={
                    "job_id": job_id,
                    "status": resume_state.get("status", "unknown"),
                },
            )
    except Exception as exc:
        logger.warning(
            "Vérification reprise ignorée",
            extra={"job_id": job_id[:8], "error": str(exc)},
        )

    # ── 3. Exécuter le pipeline ──────────────────────────────────────────
    try:
        dl_mode = "download_only" if download_only else "translate"
        logger.info(
            f"Mode={dl_mode} | job={job_id[:8]} | target_lang={target_lang}",
            extra={"job_id": job_id, "mode": dl_mode},
        )

        # Passer la cle API Groq depuis la config (sinon le worker ne l'a pas)
        # 🔑 Résolution de la clé Groq : appel à Economy via HTTP
        groq_key = ""
        try:
            import uuid as _uuid
            wallet = ""
            # Récupérer le wallet depuis la colonne user_id de jobs
            from core.db import direct_connect as _dc
            try:
                async def _get_wallet():
                    async with _dc() as _c:
                        row = await _c.fetchrow(
                            "SELECT user_id FROM jobs WHERE id=$1",
                            _uuid.UUID(job_id),
                        )
                        return (row or {}).get("user_id", "")
                import asyncio as _aio
                wallet = _aio.run(_get_wallet())
            except Exception:
                pass
            if wallet:
                import httpx
                resp = httpx.get(
                    f"{settings.ECONOMY_URL}/billing/groq-key/{wallet}",
                    timeout=5,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("key"):
                        groq_key = data["key"]
        except Exception as e:
            logger.warning(f"Groq key resolution failed: {e}")
        if not groq_key:
            groq_key = settings.GROQ_API_KEY or ""
        if not groq_key:
            # Fallback: try to use a community pool key
            try:
                import httpx as _httpx
                pool_resp = _httpx.get(
                    f"{settings.ECONOMY_URL}/billing/groq-key/pool",
                    timeout=5,
                )
                if pool_resp.status_code == 200:
                    pool_data = pool_resp.json()
                    if pool_data.get("key"):
                        groq_key = pool_data["key"]
                        logger.info("Clé Groq communautaire utilisée")
            except Exception as pe:
                logger.warning(f"Pool key fallback failed: {pe}")
        if not groq_key:
            # Direct DB fallback: query community pool keys directly
            # (workaround for Economy API FastAPI compat issue)
            try:
                import asyncio as _aio2
                import asyncpg as _apg
                from core.crypto import decrypt_groq_key as _dgk

                async def _fetch_pool_key():
                    _db = await _apg.connect(settings.DATABASE_URL)
                    try:
                        _row = await _db.fetchrow(
                            "SELECT groq_key_enc FROM subvox_groq_pool"
                            " WHERE is_active = TRUE LIMIT 1"
                        )
                        if _row:
                            _dec = _dgk(_row["groq_key_enc"])
                            if _dec and _dec.startswith("gsk_"):
                                return _dec
                        return None
                    finally:
                        await _db.close()

                _pk = _aio2.run(_fetch_pool_key())
                if _pk:
                    groq_key = _pk
                    logger.info("Clé Groq du pool (DB direct)")
            except Exception as _de:
                logger.warning(f"DB pool key failed: {_de}")
        if not groq_key:
            logger.warning("Aucune clé Groq disponible — la transcription échouera")
        # Si un _source_job_id est fourni, le pipeline peut skipper download + transcribe
        if _source_job_id:
            logger.info(
                f"Source job {_source_job_id[:8]} fourni — pipeline economise download+transcribe",
                extra={"job_id": job_id[:8], "source_job_id": _source_job_id[:8]},
            )
        soft_subs = (
            settings.SOFT_SUBS_ENABLED
            if hasattr(settings, "SOFT_SUBS_ENABLED")
            else True
        )
        result = asyncio.run(
            process_video(
                job_id,
                source_url,
                target_lang,
                user_id,
                groq_api_key=groq_key,
                _source_job_id=_source_job_id or "",
                soft_subs=soft_subs,
            )
        )

        if result and result.get("storage_url") and not result.get("_db_update_ok"):
            logger.info("DB non mise à jour par le pipeline — forcage...")
            _db._pool = None
            asyncio.run(
                _force_done_status(
                    job_id=job_id,
                    storage_url=result["storage_url"],
                    storage_key=result.get("storage_key", ""),
                    source_lang=result.get("source_lang"),
                    thumbnail_url=result.get("thumbnail_url"),
                    duration_s=int(result.get("duration_s", 0)),
                )
            )

        # Marquer comme reprise réussie : réinitialiser resume_attempts
        try:
            from core.pipeline.persist import reset_pipeline_state

            asyncio.run(reset_pipeline_state(job_id))
        except Exception:
            pass

        return result

    except Exception as exc:
        exc_str = str(exc).lower()
        retry_num = self.request.retries + 1

        no_retry_keywords = ["sign in to confirm", "not a bot", "cookies", "account"]
        is_auth_error = any(kw in exc_str for kw in no_retry_keywords)

        if is_auth_error:
            logger.error("Erreur d'authentification détectée — pas de retry")
            raise

        logger.warning(
            f"Task {job_id[:8]} échouée (essai {retry_num}/{self.max_retries + 1})",
            extra={"job_id": job_id, "error": str(exc)[:300]},
        )

        if retry_num <= self.max_retries:
            try:
                _db._pool = None

                error_msg = f"Retry {retry_num}/{self.max_retries}: {str(exc)[:200]}"

                async def _reset_status():
                    from core.db import direct_connect

                    async with direct_connect() as conn:
                        await conn.execute(
                            "UPDATE jobs SET status='queued', error_msg=$2, updated_at=now() WHERE id=$1",
                            uuid.UUID(job_id),
                            error_msg,
                        )

                asyncio.run(_reset_status())
            except Exception as db_exc:
                logger.error(f"Reset status échoué: {db_exc}")

        raise self.retry(exc=exc, countdown=120 * retry_num)


# ─── Tâche de burn asynchrone en arrière-plan ───────────────────────────────


@celery_app.task(
    name="tasks.pipeline_task.burn_job_background",
    bind=True,
    max_retries=2,
    default_retry_delay=300,
    time_limit=7200,  # 2h max
    soft_time_limit=6000,
    queue="xlong",
)
def burn_job_background(
    self,
    job_id: str,
    watermark: bool = True,
    source_job_id: str = "",
):
    """
    Tâche Celery de burn asynchrone.
    Appelée automatiquement après la fin du pipeline soft-subs.
    
    Étapes :
    1. Vérifier que le job est "done"
    2. Lire processed_steps → récupérer les données nécessaires
    3. Executer step_burn, step_watermark, step_upload
    4. Mettre à jour storage_url
    5. Marquer le burn_status = "ready"
    
    L'utilisateur peut poller GET /jobs/{jobId}/burn-status pendant l'exécution.
    """
    import core.db as _db
    _db._pool = None
    
    from core.logging_setup import get_logger as _get_logger
    _logger = _get_logger(__name__)
    
    _logger.info(
        "🔥 Burn asynchrone démarré",
        extra={"job_id": job_id[:8], "watermark": watermark},
    )
    
    try:
        # ── 1. Vérifier le job ───────────────────────────────────────────
        import uuid as _uuid
        from core.pipeline.persist import (
            save_burn_status, mark_step_completed,
            save_pipeline_file,
        )
        from core.db import direct_connect
        
        async def _run_burn():
            # Vérifier l'état
            async with direct_connect() as conn:
                row = await conn.fetchrow(
                    "SELECT status, storage_url, source_storage_url, "
                    "source_lang, target_lang, video_width, video_height "
                    "FROM jobs WHERE id=$1",
                    _uuid.UUID(job_id),
                )
            
            if not row:
                raise RuntimeError(f"Job {job_id[:8]} introuvable")
            
            status = row["status"]
            _logger.info(
                "État job pour burn asynchrone",
                extra={"job_id": job_id[:8], "status": status},
            )
            
            # Si déjà burné (storage_url != source_storage_url)
            storage_url = row["storage_url"] or ""
            source_storage_url = row["source_storage_url"] or ""
            if storage_url and source_storage_url and storage_url != source_storage_url:
                _logger.info(
                    "Vidéo déjà burnée — skip",
                    extra={"job_id": job_id[:8]},
                )
                await save_burn_status(job_id, "ready", 100, storage_url)
                return {"status": "ready", "storage_url": storage_url}
            
            # ── 2. Lire les données nécessaires ──────────────────────────
            row["source_lang"] or ""
            row["target_lang"] or ""
            row["video_width"] or 1920
            row["video_height"] or 1080
            
            # Récupérer les ASS et chemins depuis processed_files
            from core.pipeline.persist import load_step_data, get_source_mp4_path
            import json as _json
            
            ass_data = await load_step_data(job_id, "ass_generation")
            src_path = await get_source_mp4_path(job_id)
            
            if not src_path:
                # Fallback : chercher dans processed_files
                dl_data = await load_step_data(job_id, "downloading")
                pf = dl_data.get("processed_files", {})
                src_path = pf.get("source_mp4", "")
                if not src_path:
                    # Chercher dans processed_steps
                    async with direct_connect() as conn2:
                        ps_row = await conn2.fetchrow(
                            "SELECT processed_steps FROM jobs WHERE id=$1",
                            _uuid.UUID(job_id),
                        )
                        if ps_row:
                            ps = ps_row["processed_steps"] or {}
                            if isinstance(ps, str):
                                ps = _json.loads(ps)
                            src_path = ps.get("__source_mp4", "")
            
            if not src_path:
                _logger.warning(
                    "source.mp4 introuvable — tentative de téléchargement",
                    extra={"job_id": job_id[:8]},
                )
                from core.pipeline.steps import _get_tmp as _get_tmp_path
                import httpx
                import os as _os
                tmp_dir = _get_tmp_path(job_id)
                _os.makedirs(str(tmp_dir), exist_ok=True)
                src_path = str(tmp_dir / "source.mp4")
                # Essayer source_storage_url puis storage_url comme fallback
                download_urls = []
                if source_storage_url:
                    download_urls.append(("source_storage_url", source_storage_url))
                if storage_url and storage_url != source_storage_url:
                    download_urls.append(("storage_url", storage_url))
                downloaded = False
                for label, url in download_urls:
                    try:
                        # Handle file:// URLs locally instead of HTTP
                        if url.startswith("file://"):
                            local_file = url.replace("file://", "")
                            if os.path.exists(local_file):
                                shutil.copy2(local_file, src_path)
                                logger.info(f"Fichier source copié depuis {local_file}")
                                downloaded = True
                                break
                        async with httpx.AsyncClient(timeout=300.0) as client:
                            resp = await client.get(url)
                            if resp.status_code == 200:
                                with open(src_path, "wb") as f:
                                    f.write(resp.content)
                                _logger.info(
                                    f"source.mp4 téléchargé depuis {label}",
                                    extra={"job_id": job_id[:8], "url": url[:80]},
                                )
                                downloaded = True
                                break
                            else:
                                _logger.warning(
                                    f"Échec téléchargement depuis {label}: HTTP {resp.status_code}",
                                    extra={"job_id": job_id[:8], "url": url[:80]},
                                )
                    except Exception as dl_exc:
                        _logger.warning(
                            f"Exception téléchargement depuis {label}: {dl_exc}",
                            extra={"job_id": job_id[:8], "url": url[:80]},
                        )
                if not downloaded:
                    src_path = ""
            
            if not src_path or not Path(src_path).exists():
                raise RuntimeError("source.mp4 introuvable pour le burn")
            
            ass_path = ass_data.get("processed_files", {}).get("ass_path", "") if ass_data else ""
            # Toujours définir _tmp_burn pour l'utiliser plus tard (burn source)
            from core.pipeline.steps import _get_tmp as _get_tmp_path2
            _tmp_burn = _get_tmp_path2(job_id)
            if not ass_path:
                # Fallback GÉNÉRIQUE : chercher tous les .ass dans le dossier tmp
                import glob as _glob
                ass_files = _glob.glob(str(_tmp_burn / "*.ass"))
                # Prioriser subtitles.ass (traduit) sur source_subtitles.ass (original)
                preferred = [f for f in ass_files if "source_" not in Path(f).name]
                if preferred:
                    ass_path = preferred[0]
                elif ass_files:
                    ass_path = ass_files[0]
                    _logger.info(
                        "ASS trouvé par fallback glob",
                        extra={"job_id": job_id[:8], "ass_path": ass_path},
                    )
                else:
                    _logger.warning(
                        "ASS introuvable — tentative de régénération depuis les segments DB",
                        extra={"job_id": job_id[:8]},
                    )
                    # Fallback ultime : régénérer le ASS depuis les segments de transcription
                    try:
                        async with direct_connect() as conn_seg:
                            seg_rows = await conn_seg.fetch(
                                "SELECT start_time, end_time, translated_text "
                                "FROM transcription_segments WHERE job_id=$1 "
                                "ORDER BY start_time ASC",
                                _uuid.UUID(job_id),
                            )
                        if seg_rows:
                            tmp_dir = str(_tmp_burn)
                            import os as _os
                            _os.makedirs(tmp_dir, exist_ok=True)
                            srt_lines = []
                            for i, seg in enumerate(seg_rows, 1):
                                txt = seg["translated_text"] or ""
                                if txt.strip():
                                    start = float(seg["start_time"])
                                    end = float(seg["end_time"])
                                    srt_lines.append(str(i))
                                    # Format SRT correct : HH:MM:SS,mmm
                                    def _sec_to_srt(sec: float) -> str:
                                        h = int(sec // 3600)
                                        m = int((sec % 3600) // 60)
                                        s = sec % 60
                                        return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".", ",")
                                    srt_lines.append(
                                        f"{_sec_to_srt(start)} --> {_sec_to_srt(end)}"
                                    )
                                    srt_lines.append(txt.strip())
                                    srt_lines.append("")
                            if srt_lines:
                                srt_path = f"{tmp_dir}/fallback.srt"
                                with open(srt_path, "w") as f:
                                    f.write("\n".join(srt_lines))
                                _logger.info(
                                    "SRT fallback généré depuis les segments DB",
                                    extra={"job_id": job_id[:8], "segments": len(seg_rows)},
                                )
                                # Appeler step_ass_generation avec ce SRT
                                from core.pipeline.steps import step_ass_generation
                                ass_result = await step_ass_generation(
                                    job_id,
                                    srt_to_burn=open(srt_path).read(),
                                    source_path_override=src_path,
                                )
                                if ass_result and ass_result.files:
                                    ass_path = ass_result.files.get("ass_path", "")
                                if not ass_path:
                                    # Dernier recours : chercher le fichier généré
                                    ass_files2 = _glob.glob(str(_tmp_burn / "*.ass"))
                                    if ass_files2:
                                        ass_path = ass_files2[0]
                                    else:
                                        ass_path = ""
                    except Exception as ass_exc:
                        import traceback as _traceback
                        _logger.error(
                            "Échec régénération ASS fallback",
                            extra={
                                "job_id": job_id[:8],
                                "error": str(ass_exc)[:200],
                                "traceback": _traceback.format_exc()[-500:],
                            },
                        )
                    if not ass_path or not Path(ass_path).exists():
                        raise RuntimeError("ASS introuvable pour le burn")
            
            _logger.info(
                "Fichiers prêts pour le burn",
                extra={
                    "job_id": job_id[:8],
                    "src_path": src_path,
                    "ass_path": ass_path,
                },
            )
            
            # ── 3. Executer step_burn pour la langue traduite ──────────────
            await save_burn_status(job_id, "burning", 10)
            
            from core.pipeline.steps import step_burn
            
            def _on_burn_progress(pct: int):
                pass
            
            _logger.info("Burn FFmpeg (langue traduite)...", extra={"job_id": job_id[:8]})
            
            burn_result = await step_burn(job_id, on_progress=None)
            
            if not burn_result or not burn_result.success:
                raise RuntimeError(
                    f"Etape burn échouée: {burn_result.error if burn_result else 'unknown'}"
                )
            
            await save_burn_status(job_id, "burning", 40)
            
            # Sauvegarder et uploader la vidéo traduite
            burned_path = ""
            if hasattr(burn_result, "files") and burn_result.files:
                burned_path = burn_result.files.get("burned_mp4", "")
            if burned_path:
                await save_pipeline_file(job_id, "burning", "burned_mp4", burned_path)
            
            await mark_step_completed(job_id, "burning")
            _logger.info("Burn traduit terminé", extra={"job_id": job_id[:8]})
            
            # ── 3b. Upload vidéo traduite ─────────────────────────────────
            from core.pipeline.steps import step_upload
            _logger.info("Upload vidéo traduite...", extra={"job_id": job_id[:8]})
            upload_result = await step_upload(job_id)
            
            if not upload_result or not upload_result.success:
                raise RuntimeError(
                    f"Upload vidéo traduite échoué: {upload_result.error if upload_result else 'unknown'}"
                )
            
            translated_storage_key = upload_result.data.get("storage_url", "")
            _logger.info(
                "Upload traduit terminé",
                extra={"job_id": job_id[:8], "url": translated_storage_key[:80] if translated_storage_key else "empty"},
            )
            
            # ── 3c. Burn + upload langue SOURCE (sous-titres originaux) ──
            _logger.info("Burn FFmpeg (langue source)...", extra={"job_id": job_id[:8]})
            source_ass = _tmp_burn / "source_subtitles.ass"
            if source_ass.exists():
                # Burn avec le ASS source
                source_burn_result = await step_burn(job_id, on_progress=None, ass_path_override=str(source_ass))
                
                if source_burn_result and source_burn_result.success:
                    # Uploader le résultat source
                    source_burned_path = ""
                    if hasattr(source_burn_result, "files") and source_burn_result.files:
                        source_burned_path = source_burn_result.files.get("burned_mp4", "")
                    
                    if source_burned_path:
                        await save_pipeline_file(job_id, "burning", "source_burned_mp4", source_burned_path)
                    
                    # Upload avec préfixe source_
                    try:
                        source_upload_result = await step_upload(job_id, prefix="source_")
                        source_storage_key = source_upload_result.data.get("storage_url", "") if source_upload_result else ""
                        _logger.info(
                            "Upload source terminé",
                            extra={"job_id": job_id[:8], "url": source_storage_key[:80] if source_storage_key else "empty"},
                        )
                    except Exception as src_up_exc:
                        _logger.warning(
                            "Upload source ignoré",
                            extra={"job_id": job_id[:8], "error": str(src_up_exc)[:200]},
                        )
                        source_storage_key = ""
                else:
                    _logger.warning("Burn source ignoré (échec)", extra={"job_id": job_id[:8]})
                    source_storage_key = ""
            else:
                _logger.info("source_subtitles.ass introuvable, skip burn source", extra={"job_id": job_id[:8]})
                source_storage_key = ""
            
            # ── 4. Watermark (optionnel) ─────────────────────────────────
            if watermark:
                await save_burn_status(job_id, "watermarking", 60)
                # Le watermark est géré dans step_burn ou step_watermark
                # Si le pipeline a déjà watermarké, skip
                from core.pipeline.persist import get_completed_steps
                completed = await get_completed_steps(job_id)
                if "watermark" not in completed:
                    from core.pipeline.steps import step_watermark
                    wm_result = await step_watermark(job_id)
                    if wm_result and wm_result.success:
                        await mark_step_completed(job_id, "watermark")
                        _logger.info("Watermark ajouté", extra={"job_id": job_id[:8]})
                    else:
                        _logger.warning(
                            "Watermark ignoré (pas d'image ou erreur)",
                            extra={"job_id": job_id[:8]},
                        )
            
            # ── 5. Upload Supabase ───────────────────────────────────────
            await save_burn_status(job_id, "uploading", 70)
            
            from core.pipeline.steps import step_upload
            upload_result = await step_upload(job_id)
            
            if not upload_result or not upload_result.success:
                raise RuntimeError(
                    f"Upload après burn échoué: {upload_result.error if upload_result else 'unknown'}"
                )
            
            storage_key = upload_result.data.get("storage_url", "")
            _logger.info(
                "Upload terminé après burn",
                extra={
                    "job_id": job_id[:8],
                    "storage_url": storage_key[:80] if storage_key else "empty",
                },
            )
            
            # ── 6. Mettre à jour le job en DB ────────────────────────────
            async with direct_connect() as conn:
                # Construire l'objet burned_languages pour stocker les 2 URLs
                burned_langs = json.dumps({
                    "fr": translated_storage_key,
                    "en": source_storage_key or "",
                })
                await conn.execute(
                    "UPDATE jobs SET "
                    "storage_url=$2, step_data=step_data::jsonb || $3::jsonb, updated_at=now() "
                    "WHERE id=$1",
                    _uuid.UUID(job_id),
                    translated_storage_key,
                    json.dumps({"burned_languages": {"fr": translated_storage_key, "en": source_storage_key or ""}}),
                )
            
            await save_burn_status(job_id, "ready", 100, translated_storage_key)
            
            _logger.info(
                "🔥 Burn asynchrone terminé avec succès",
                extra={"job_id": job_id[:8], "storage_url": translated_storage_key[:80]},
            )
            
            return {"status": "ready", "storage_url": translated_storage_key}
        
        result = asyncio.run(_run_burn())
        return result
    
    except Exception as exc:
        _logger.error(
            "🔥 Burn asynchrone échoué",
            extra={
                "job_id": job_id[:8],
                "error": str(exc)[:300],
            },
        )
        try:
            asyncio.run(
                save_burn_status(job_id, "error", 0)
            )
        except Exception:
            pass
        raise
