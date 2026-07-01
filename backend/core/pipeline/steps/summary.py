"""
Étape 4 : Résumé LLM adaptatif.
"""

from __future__ import annotations

from core.logging_setup import get_logger
from core.config import settings
from core.pipeline.duration_tiers import DurationTier
from core.pipeline.steps._types import StepResult

logger = get_logger(__name__)


async def step_summary(
    job_id: str,
    transcript_tx: str = "",
    source_lang: str = "en",
    target_lang: str = "fr",
    video_title: str = "",
    video_description: str = "",
    duration_tier: DurationTier | None = None,
) -> StepResult:
    """
    Génère un résumé adaptatif de la vidéo via Qwen local (priorité)
    ou OpenRouter DeepSeek V3 (fallback).
    """
    from core.local_llm import generate_summary_local
    from core.openrouter import generate_adaptive_summary

    log_extra = {"job_id": job_id}
    summary = ""
    summary_saved = False
    segments_data: list[dict] | None = None

    # Guard : vérifier que le transcript n'est pas vide avant d'appeler le LLM
    if not transcript_tx or len(transcript_tx.strip()) < 100:
        logger.warning(
            "Résumé ignoré : transcript vide ou trop court (%d chars)",
            len(transcript_tx) if transcript_tx else 0,
            extra=log_extra,
        )
        return StepResult(
            data={
                "summary": "",
                "summary_saved": False,
                "target_lang": target_lang,
                "char_count": 0,
                "segments": [],
                "reason": "transcript_vide",
            }
        )

    title = ""
    category = ""

    try:
        # Priorité : Qwen local (gratuit, hors-ligne) → OpenRouter
        local_result = await generate_summary_local(
            transcript_tx,
            source_lang=source_lang,
            target_lang=target_lang,
            video_title=video_title,
        )
        adaptive_result = None

        if local_result:
            summary = local_result.get("global_summary", "")
            title = local_result.get("title", "")
            category = local_result.get("category", "")
            segments_data = []
            logger.info(
                f"Resume Qwen local OK: title={title[:40]} summary={len(summary)} chars",
                extra=log_extra,
            )
        elif settings.llm_enabled:
            adaptive_result = await generate_adaptive_summary(
                transcript_tx,
                source_lang=source_lang,
                target_lang=target_lang,
                video_title=video_title,
                video_description=video_description,
                user_id=f"job_{job_id}",
            )
            if adaptive_result:
                summary = adaptive_result.get("global_summary", "")
                segments_data = adaptive_result.get("segments", [])
                title = adaptive_result.get("title", "")
                category = adaptive_result.get("category", "")

                # Valider les segments
                if segments_data:
                    valid_segments = []
                    for idx, seg in enumerate(segments_data):
                        if not isinstance(seg, dict):
                            logger.warning("Segment ignore (pas un dict)", extra={"job_id": job_id, "index": idx})
                            continue
                        ts = seg.get("timestamp")
                        ss = seg.get("start_s")
                        if not ts or not isinstance(ts, str):
                            logger.warning("Segment ignore: timestamp manquant", extra={"job_id": job_id, "index": idx})
                            continue
                        if ss is None or not isinstance(ss, (int, float)) or ss < 0:
                            logger.warning("Segment ignore: start_s invalide", extra={"job_id": job_id, "index": idx})
                            continue
                        valid_segments.append(seg)
                    segments_data = valid_segments
                    logger.info("Segments valides apres filtre: %d sur %d", len(valid_segments), len(segments_data), extra=log_extra)
        else:
            logger.info("Qwen indisponible + LLM desactive -- skip resume", extra=log_extra)

        # ── Sauvegarder le résultat (Qwen ou OpenRouter) ──
        if summary or segments_data:
            from core.pipeline.persist import save_step_data
            from datetime import datetime, timezone

            now_iso = datetime.now(timezone.utc).isoformat()
            summary_payload = {
                target_lang: {
                    "title": title,
                    "category": category,
                    "text": summary,
                    "segments": segments_data,
                    "tier": adaptive_result.get("tier", 1) if adaptive_result else 1,
                    "generated_at": now_iso,
                }
            }
            await save_step_data(job_id, "summary", summary_payload)
            summary_saved = True

            # Sauvegarder title + category directement dans jobs
            from core.db import get_conn as _get_conn2

            conn2 = await _get_conn2()
            if title:
                await conn2.execute(
                    "UPDATE jobs SET title=$1, updated_at=now() WHERE id=$2",
                    title[:500],
                    __import__("uuid").UUID(job_id),
                )
            if category:
                await conn2.execute(
                    "UPDATE jobs SET category=$1, updated_at=now() WHERE id=$2",
                    category[:50],
                    __import__("uuid").UUID(job_id),
                )
            await conn2.close()

        if summary:
            logger.info(
                f"Resume genere ({len(summary)} car., {len(segments_data or [])} segments) pour {target_lang}",
                extra=log_extra,
            )
            if title:
                logger.info(f"Titre: {title}", extra=log_extra)
        else:
            logger.warning("Aucun resume genere", extra=log_extra)

    except Exception as e:
        logger.warning("Resume ignore", extra={"error": str(e), **log_extra})

    return StepResult(
        data={
            "summary": summary,
            "summary_saved": summary_saved,
            "target_lang": target_lang,
            "char_count": len(summary),
            "segments": segments_data or [],
            "title": title,
            "category": category,
        }
    )
