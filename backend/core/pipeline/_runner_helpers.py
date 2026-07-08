"""
_runner_helpers.py — Helpers extraits de runner.py pour alléger l'orchestrateur.

Contient :
  - _set_status / _update_progress / _heartbeat      (ex-fonctions imbriquées)
  - _copy_source_job_data                              (ex-bloc Mission 6)
  - _finalize_pipeline                                 (ex-bloc finalisation DB)
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx
from core.db import direct_connect as _direct
from core.logging_setup import get_logger
from core.pipeline.metrics import MetricsCollector
from core.pipeline.persist import (
    mark_step_completed,
    save_step_data,
    load_filtered_srt,
    save_vtt_urls,
)

logger = get_logger(__name__)


# ─── Helpers DB (ex-fonctions imbriquées) ───────────────────────────────────


async def _set_status(job_id: str, status: str, error_msg: str = "") -> None:
    """Met à jour le statut du job en DB."""
    from uuid import UUID
    try:
        async with _direct() as conn:
            await conn.execute(
                "UPDATE jobs SET status=$1, error_msg=$2, updated_at=now() WHERE id=$3",
                status,
                error_msg or None,
                UUID(job_id),
            )
    except Exception as exc:
        logger.warning("DB status update ignore", extra={"error": str(exc)})


async def _update_progress(
    job_id: str,
    progress_pct: int,
    status: str = "",
    _last_pct_store: list[int] | None = None,
    _last_time_store: list[float] | None = None,
) -> None:
    """
    Met à jour le pourcentage de progression en DB avec throttle.
    Utilise des listes mutables comme store pour persister l'état entre appels.
    """
    from uuid import UUID
    import time as _time

    if _last_pct_store is None:
        _last_pct_store = [-1]
    if _last_time_store is None:
        _last_time_store = [0.0]

    last_pct = _last_pct_store[0]
    last_time = _last_time_store[0]

    # Throttle même pourcentage
    if status == "burning" and progress_pct == last_pct:
        return

    # Throttle temporel : max 1 écriture DB toutes les 2 secondes
    now = _time.monotonic()
    if status == "burning" and now - last_time < 2.0:
        return

    _last_pct_store[0] = progress_pct
    _last_time_store[0] = now

    try:
        async with _direct() as conn:
            if status:
                await conn.execute(
                    "UPDATE jobs SET status=$1, progress_pct=$2, updated_at=now() WHERE id=$3",
                    status,
                    progress_pct,
                    UUID(job_id),
                )
            else:
                await conn.execute(
                    "UPDATE jobs SET progress_pct=$1, updated_at=now() WHERE id=$2",
                    progress_pct,
                    UUID(job_id),
                )
    except Exception as exc:
        logger.warning(
            "DB progress update ignore",
            extra={
                "error": str(exc),
                "progress_pct": progress_pct,
                "job_id": job_id,
                "status": status,
            },
        )


# ─── Heartbeat ──────────────────────────────────────────────────────────────


_heartbeat_running: dict[str, bool] = {}


async def _keepalive(job_id: str) -> None:
    """Boucle de heartbeat : update updated_at toutes les 10s."""
    _heartbeat_running[job_id] = True
    try:
        while _heartbeat_running.get(job_id, False):
            await asyncio.sleep(10)
            try:
                from uuid import UUID
                async with _direct() as conn:
                    await conn.execute(
                        "UPDATE jobs SET updated_at=now() WHERE id=$1",
                        UUID(job_id),
                    )
            except Exception:
                pass
    except asyncio.CancelledError:
        pass
    finally:
        _heartbeat_running[job_id] = False


async def _start_heartbeat(job_id: str) -> None:
    """Lance le heartbeat en arrière-plan."""
    if _heartbeat_running.get(job_id, False):
        return
    asyncio.create_task(_keepalive(job_id))


async def _stop_heartbeat(job_id: str) -> None:
    """Arrête le heartbeat."""
    _heartbeat_running[job_id] = False


# ─── Mission 6 : Copie des données du job source (ex-bloc dans run_pipeline) ─


async def _copy_source_job_data(
    job_id: str,
    source_job_id: str,
    tmp: Path,
    completed: set[str],
) -> tuple[float, str, str | None, str, str | None]:
    """
    Copie les données de download + transcribe + filter depuis un job source.
    Retourne (duration, source_lang, thumbnail_url, video_type, source_storage_url).
    Lève une exception en cas d'échec (fallback vers pipeline normal).
    """
    from uuid import UUID
    from core.pipeline.metrics import get_collector

    metrics = get_collector(job_id)
    duration = 0.0
    source_lang = ""
    thumbnail_url: str | None = None
    video_type = "long"
    source_storage_url: str | None = None

    async with _direct() as conn:
        src_row = await conn.fetchrow(
            "SELECT source_storage_url, source_lang, duration_s, video_type, thumbnail_url, "
            "processed_files, transcription_json FROM jobs WHERE id=$1",
            UUID(source_job_id),
        )
        if not src_row or not src_row["source_storage_url"]:
            raise ValueError("Job source introuvable ou pas de source_storage_url")

        d_src = float(src_row["duration_s"] or 0)
        sl_src = src_row["source_lang"] or "en"
        vt_src = src_row["video_type"] or "long"
        tn_src = src_row["thumbnail_url"]
        ssu_src = src_row["source_storage_url"]
        dl_data = {
            "source_storage_url": ssu_src,
            "duration_s": d_src,
            "source_lang": sl_src,
            "video_type": vt_src,
            "thumbnail_url": tn_src,
        }
        await save_step_data(job_id, "downloading", dl_data)
        await mark_step_completed(job_id, "downloading")

        # Copier source.mp4 depuis Supabase Storage
        source_mp4_path = tmp / "source.mp4"
        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                resp = await client.get(ssu_src)
                if resp.status_code == 200:
                    source_mp4_path.write_bytes(resp.content)
                    logger.info(
                        "source.mp4 copié depuis Supabase Storage",
                        extra={
                            "job_id": job_id[:8],
                            "size_mb": round(len(resp.content) / 1024 / 1024, 1),
                        },
                    )
                else:
                    raise RuntimeError(f"HTTP {resp.status_code}")
        except Exception as dl_exc:
            logger.warning(
                "Échec copie source.mp4 depuis Supabase — re-download forcé",
                extra={"job_id": job_id[:8], "error": str(dl_exc)},
            )
            if source_mp4_path.exists():
                source_mp4_path.unlink()
            completed.discard("downloading")
            completed.discard("transcribing")
            completed.discard("filtering")
            raise

        duration = d_src
        source_lang = sl_src
        thumbnail_url = tn_src
        video_type = vt_src
        source_storage_url = ssu_src
        completed.add("downloading")

        logger.info(
            "Download skippé via _source_job_id",
            extra={"job_id": job_id[:8], "source_job_id": source_job_id[:8]},
        )

        # Copier transcription_json
        tx_json = src_row["transcription_json"]
        if tx_json:
            tx_data = tx_json if isinstance(tx_json, dict) else {}
            await save_step_data(job_id, "transcribing", tx_data)
            await mark_step_completed(job_id, "transcribing")
            completed.add("transcribing")
            logger.info(
                "Transcribe skippé via _source_job_id",
                extra={"job_id": job_id[:8], "source_job_id": source_job_id[:8]},
            )

        # Copier transcription_segments
        seg_rows = await conn.fetch(
            "SELECT start_time, end_time, original_text, translated_text, style, custom_order "
            "FROM transcription_segments WHERE job_id=$1 ORDER BY start_time",
            UUID(source_job_id),
        )
        if seg_rows:
            for seg in seg_rows:
                await conn.execute(
                    "INSERT INTO transcription_segments "
                    "(id, job_id, start_time, end_time, original_text, translated_text, style, custom_order) "
                    "VALUES ($1, $2, $3, $4, $5, $6, $7, $8)",
                    uuid.uuid4(),
                    UUID(job_id),
                    seg["start_time"],
                    seg["end_time"],
                    seg["original_text"] or "",
                    seg["translated_text"] or "",
                    seg["style"] or "classique",
                    seg["custom_order"] or 0,
                )
            logger.info(
                f"{len(seg_rows)} transcription_segments copiés depuis job source",
                extra={"job_id": job_id[:8], "source_job_id": source_job_id[:8]},
            )

        # Copier filtered SRT
        src_filtered_srt = await load_filtered_srt(source_job_id, source_lang)
        if src_filtered_srt:
            await save_step_data(job_id, "filtering", {"raw_srt": src_filtered_srt})
            await mark_step_completed(job_id, "filtering")
            completed.add("filtering")
            logger.info(
                "Mission 6 : Filter skippé — SRT filtré réutilisé depuis job source",
                extra={"job_id": job_id[:8], "source_job_id": source_job_id[:8]},
            )

        metrics.set_meta(
            source_url=source_job_id,
            source_lang=source_lang,
            target_lang="",
        )

    return duration, source_lang, thumbnail_url, video_type, source_storage_url


async def _find_source_job(source_url: str) -> str:
    """
    Détection automatique d'un job source (Mission 6).
    Retourne l'ID du job source ou chaîne vide si non trouvé.
    """
    try:
        async with _direct() as conn:
            src_row = await conn.fetchrow(
                "SELECT id FROM jobs "
                "WHERE source_url=$1 AND status='done' AND raw_srt IS NOT NULL "
                "ORDER BY created_at DESC LIMIT 1",
                source_url,
            )
            if src_row:
                found_srt = await load_filtered_srt(str(src_row["id"]), "")
                if found_srt:
                    return str(src_row["id"])
    except Exception as exc:
        logger.warning(
            "Mission 6 : Détection auto échouée",
            extra={"error": str(exc), "source_url": source_url[:50]},
        )
    return ""


# ─── Helper reprise : source.mp4 via API Supabase (solution structurelle) ──


async def _ensure_source_mp4(
    job_id: str,
    tmp: Path,
    source_storage_url: str | None,
) -> bool:
    """
    Vérifie que source.mp4 est présent sur le disque avant chaque étape
    qui en a besoin. Si absent, le re-télécharge depuis Supabase Storage
    via l'URL stockée dans la DB.

    Retourne True si source.mp4 est disponible après l'opération.
    Solution structurelle pour le Bug #2 : les fichiers temporaires ne survivent
    pas au redémarrage du worker (Railway reset, Celery retry).
    """
    source_mp4_path = tmp / "source.mp4"
    if source_mp4_path.exists():
        return True

    if not source_storage_url:
        # Fallback : charger depuis la DB via processed_files
        from core.pipeline.persist import load_step_data as _load_ps
        dl_data = await _load_ps(job_id, "downloading")
        if dl_data:
            source_storage_url = dl_data.get("source_storage_url") or \
                dl_data.get("processed_files", {}).get("source_storage_url")
        if not source_storage_url:
            # Ultime fallback : re-télécharger complètement la vidéo
            from uuid import UUID
            try:
                async with _direct() as conn:
                    row = await conn.fetchrow(
                        "SELECT source_url, source_storage_url FROM jobs WHERE id=$1",
                        UUID(job_id),
                    )
                    if row:
                        source_storage_url = row.get("source_storage_url")
                        row.get("source_url", "")
            except Exception:
                pass

    if source_storage_url:
        try:
            tmp.mkdir(parents=True, exist_ok=True)
            async with httpx.AsyncClient(timeout=300.0) as client:
                resp = await client.get(source_storage_url)
                if resp.status_code == 200:
                    source_mp4_path.write_bytes(resp.content)
                    logger.info(
                        "source.mp4 re-téléchargé depuis Supabase Storage",
                        extra={
                            "job_id": job_id[:8],
                            "size_mb": round(len(resp.content) / 1024 / 1024, 1),
                            "url": source_storage_url[:60],
                        },
                    )
                    return True
                else:
                    logger.warning(
                        "Re-téléchargement source.mp4 échoué — HTTP {code}",
                        extra={"job_id": job_id[:8], "code": resp.status_code},
                    )
        except Exception as exc:
            logger.warning(
                "Re-téléchargement source.mp4 échoué",
                extra={"job_id": job_id[:8], "error": str(exc)},
            )
    else:
        logger.warning(
            "source_storage_url introuvable — impossible de re-télécharger source.mp4",
            extra={"job_id": job_id[:8]},
        )

    return False


# ─── Finalisation DB (ex-bloc final) ────────────────────────────────────────


async def _finalize_pipeline(
    job_id: str,
    storage_key: str,
    summary: str,
    source_lang: str,
    duration: float,
    video_type: str,
    thumbnail_url: str | None,
    source_storage_url: str | None,
    video_width: int,
    video_height: int,
    vtt_storage_url: str,
    vtt_source_storage_url: str,
    target_lang: str,
    source_sub_url: str | None,
    soft_subs: bool,
    metrics: MetricsCollector,
    log_extra: dict | None = None,
) -> dict:
    """
    Finalisation DB : écrit les champs finaux du job, les URLs VTT,
    les métriques et retourne le dict de résultat.
    """
    from uuid import UUID

    log_extra = log_extra or {}
    _db_update_ok = False

    async with _direct() as conn:
        update_data = {
            "status": "done",
            "storage_url": storage_key,
            "summary": summary or None,
            "source_lang": source_lang,
            "duration_s": duration,
            "video_type": video_type,
            "thumbnail_url": thumbnail_url,
            "source_storage_url": source_storage_url,
            "video_width": video_width,
            "video_height": video_height,
            "updated_at": datetime.now(timezone.utc),
        }

        row = await conn.fetchrow(
            "SELECT processed_steps FROM jobs WHERE id=$1",
            UUID(job_id),
        )
        if row:
            ps = row.get("processed_steps") or {}
            if isinstance(ps, str):
                try:
                    ps = json.loads(ps)
                except Exception:
                    ps = {}
            if vtt_storage_url or vtt_source_storage_url:
                await save_vtt_urls(
                    job_id=job_id,
                    vtt_url=vtt_storage_url or "",
                    vtt_source_url=vtt_source_storage_url or "",
                    target_lang=target_lang,
                    source_lang=source_lang,
                )
                row2 = await conn.fetchrow(
                    "SELECT processed_steps FROM jobs WHERE id=$1",
                    UUID(job_id),
                )
                if row2:
                    ps2 = row2.get("processed_steps") or {}
                    if isinstance(ps2, str):
                        try:
                            ps2 = json.loads(ps2)
                        except Exception:
                            ps2 = {}
                    ps.update(ps2)
                    update_data["processed_steps"] = json.dumps(ps)
                else:
                    if vtt_storage_url:
                        ps["__vtt_url"] = vtt_storage_url
                        ps[f"__vtt_url_{target_lang}"] = vtt_storage_url
                    if vtt_source_storage_url:
                        ps["__vtt_source_url"] = vtt_source_storage_url
                        ps[f"__vtt_source_url_{source_lang}"] = vtt_source_storage_url
                    update_data["processed_steps"] = json.dumps(ps)

        await conn.execute(
            """UPDATE jobs SET
            status='done', storage_url=$1, summary=$2,
            source_lang=$3, duration_s=$4, video_type=$5,
            thumbnail_url=$6, source_storage_url=$7,
            video_width=$8, video_height=$9,
            source_sub_url=$10,
            processed_steps=$11,
            updated_at=now()
            WHERE id=$12""",
            storage_key,
            summary or None,
            source_lang,
            duration,
            video_type,
            thumbnail_url,
            source_storage_url,
            video_width,
            video_height,
            source_sub_url,
            update_data.get("processed_steps", None),
            UUID(job_id),
        )
    _db_update_ok = True

    metrics_data = metrics.finalize()

    vm = metrics_data.get("video", {}) or {}
    v_str = f"{vm.get('width', '?')}x{vm.get('height', '?')} {vm.get('codec', '?')} {vm.get('file_size_mb', 0)}MB {vm.get('duration_s', 0)}s"

    sm = metrics_data.get("subtitles", {}) or {}
    s_str = f"{sm.get('total_lines', 0)} lignes ASS={sm.get('ass_file_size_kb', 0)}KB font={sm.get('font_size', 14)}"

    cm = metrics_data.get("cost", {}) or {}
    llm_cost = cm.get("llm_summary_eur", 0) + cm.get("llm_translation_eur", 0)
    c_str = (
        f"Groq:{cm.get('groq_eur', 0)}€+"
        f"LLM:{llm_cost}€="
        f"{cm.get('total_eur', 0)}€"
    )

    steps_m = metrics_data.get("steps", {}) or {}
    steps_str = " ".join(
        f"{n}={s.get('duration_s', 0):.1f}s" for n, s in steps_m.items()
    )

    total_dur = metrics_data.get("total_duration_s", 0.0)
    logger.info(
        f"Pipeline termine — mode={'soft_subs' if soft_subs else 'burn'} | "
        f"job={job_id[:8]} | "
        f"video={v_str} | "
        f"sous-titres={s_str} | "
        f"vtt_url={'oui' if vtt_storage_url else 'non'} | "
        f"cout={c_str} | "
        f"etapes: {steps_str} | "
        f"total={total_dur:.1f}s",
        extra=log_extra,
    )

    # ── Phase 3.2 : Créditer le publisher original pour les retraductions ──
    if _db_update_ok:
        await _credit_retraduction_publisher(job_id, log_extra)

    return {
        "storage_url": storage_key,
        "summary": summary,
        "source_lang": source_lang,
        "duration_s": duration,
        "video_type": video_type,
        "_db_update_ok": _db_update_ok,
        "thumbnail_url": thumbnail_url,
        "source_storage_url": source_storage_url,
        "source_sub_url": source_sub_url,
        "vtt_url": vtt_storage_url if soft_subs else "",
    }


# ─── Phase 3.2 : Créditer le publisher original d'une retraduction ────────


async def _credit_retraduction_publisher(job_id: str, log_extra: dict | None = None) -> bool:
    """Crédite le publisher original quand une retraduction est terminée.

    Quand un job a parent_job_id (retraduction), on crédite le wallet du
    publisher original avec 50% du coût de la retraduction.
    """
    log_extra = log_extra or {}
    try:
        async with _direct() as conn:
            # 1. Vérifier si ce job est une retraduction
            row = await conn.fetchrow(
                """SELECT j.parent_job_id, j.cost_breakdown, pj.user_id AS parent_user_id
                   FROM jobs j
                   JOIN jobs pj ON j.parent_job_id = pj.id
                   WHERE j.id = $1
                     AND j.parent_job_id IS NOT NULL
                     AND j.status = 'done'""",
                uuid.UUID(job_id),
            )
            if not row:
                return False

            cost_bd = row["cost_breakdown"]
            if not cost_bd or not isinstance(cost_bd, dict):
                return False

            # Check if already credited (idempotency via cost_breakdown tracking)
            if cost_bd.get("retraduction_credited_at"):
                return False

            publisher_share = cost_bd.get("publisher_share", 0)
            parent_user_id = row["parent_user_id"]
            parent_user_id_str = str(parent_user_id) if parent_user_id else None

            if not parent_user_id_str or publisher_share <= 0:
                return False

            # 2. Ensure holder exists
            await conn.execute(
                """INSERT INTO subvox_token_holders (wallet_address, balance, staked_amount, total_earned, total_spent)
                   VALUES ($1, 0, 0, 0, 0)
                   ON CONFLICT (wallet_address) DO NOTHING""",
                parent_user_id_str,
            )

            # 3. Credit publisher with 50% share
            await conn.execute(
                """UPDATE subvox_token_holders
                   SET balance = balance + $1, total_earned = total_earned + $1, updated_at = now()
                   WHERE wallet_address = $2""",
                publisher_share, parent_user_id_str,
            )

            # 4. Record the transaction
            await conn.execute(
                """INSERT INTO subvox_transactions (from_wallet, to_wallet, amount, tx_type, job_id, metadata)
                   VALUES ($1, $2, $3, $4, $5, $6::jsonb)""",
                "retraduction_pool",
                parent_user_id_str,
                publisher_share,
                "retraduction_publisher_reward",
                uuid.UUID(job_id),
                json.dumps({"reason": "retraduction_publisher_share", "pct": 50}),
            )

            # 5. Mark as credited (tracking flag — needs column, but we can use
            #    cost_breakdown to avoid schema change)
            existing_cb = dict(cost_bd) if cost_bd else {}
            existing_cb["retraduction_credited_at"] = datetime.now(timezone.utc).isoformat()
            await conn.execute(
                "UPDATE jobs SET cost_breakdown = $1::jsonb WHERE id = $2",
                json.dumps(existing_cb),
                uuid.UUID(job_id),
            )

            logger.info(
                f"Publisher credited {publisher_share} SUBVOX for retraduction "
                f"job={job_id[:8]} parent_user={parent_user_id_str[:10]}",
                extra=log_extra,
            )
            return True

    except Exception as exc:
        logger.warning(
            "Retraduction publisher credit failed",
            extra={"error": str(exc), "job_id": job_id[:8], **(log_extra or {})},
        )
        return False