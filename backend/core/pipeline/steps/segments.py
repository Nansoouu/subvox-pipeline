"""
Étape 6 : Sauvegarde des segments de transcription.
"""

from __future__ import annotations

import uuid

from core.logging_setup import get_logger
from core.pipeline.srt import _parse_srt, _parse_time_to_seconds
from core.pipeline.steps._helpers import _get_tmp
from core.pipeline.steps._types import StepResult

logger = get_logger(__name__)


async def step_segments_save(
    job_id: str,
    raw_srt: str = "",
    srt_to_burn: str = "",
) -> StepResult:
    """
    Sauvegarde les segments originaux et traduits dans transcription_segments.
    """
    from uuid import UUID

    log_extra = {"job_id": job_id}

    if not raw_srt:
        tmp = _get_tmp(job_id)
        srt_path = tmp / "transcript.srt"
        if srt_path.exists():
            raw_srt = srt_path.read_text(encoding="utf-8")

    if not srt_to_burn:
        srt_to_burn = raw_srt
    if not srt_to_burn:
        return StepResult(data={"segments_saved": 0})

    try:
        blocks_original = _parse_srt(raw_srt)
        blocks_translated = _parse_srt(srt_to_burn)

        if blocks_translated and len(blocks_translated) == len(blocks_original):
            from core.db import direct_connect as _direct

            async with _direct() as conn:
                await conn.execute(
                    "DELETE FROM transcription_segments WHERE job_id=$1",
                    UUID(job_id),
                )

                for idx, (orig, trans) in enumerate(
                    zip(blocks_original, blocks_translated)
                ):
                    sid = uuid.uuid4()
                    start_end = orig["timecode"].split(" --> ")
                    s = _parse_time_to_seconds(start_end[0])
                    e = (
                        _parse_time_to_seconds(start_end[1])
                        if len(start_end) > 1
                        else s + 2
                    )

                    await conn.execute(
                        """INSERT INTO transcription_segments
                        (id, job_id, original_text, translated_text,
                         start_time, end_time, custom_order)
                        VALUES ($1, $2, $3, $4, $5, $6, $7)""",
                        sid,
                        UUID(job_id),
                        orig["text"],
                        trans["text"],
                        s,
                        e,
                        (idx + 1) * 10,
                    )

            logger.info(
                f"{len(blocks_translated)} segments sauvegardes en DB",
                extra=log_extra,
            )
            return StepResult(data={"segments_saved": len(blocks_translated)})
        else:
            logger.warning(
                f"Nombre de blocs different (original: {len(blocks_original)}, "
                f"traduit: {len(blocks_translated)}) -- fallback: sauvegarde segments originaux uniquement",
                extra=log_extra,
            )
            # Fallback: sauvegarder au moins les segments originaux avec translated_text vide
            try:
                from core.db import direct_connect as _direct

                async with _direct() as conn:
                    await conn.execute(
                        "DELETE FROM transcription_segments WHERE job_id=$1",
                        UUID(job_id),
                    )
                    for idx, orig in enumerate(blocks_original):
                        sid = uuid.uuid4()
                        start_end = orig["timecode"].split(" --> ")
                        s = _parse_time_to_seconds(start_end[0])
                        e = (
                            _parse_time_to_seconds(start_end[1])
                            if len(start_end) > 1
                            else s + 2
                        )
                        await conn.execute(
                            """INSERT INTO transcription_segments
                            (id, job_id, original_text, translated_text,
                             start_time, end_time, custom_order)
                            VALUES ($1, $2, $3, $4, $5, $6, $7)""",
                            sid,
                            UUID(job_id),
                            orig["text"],
                            "",
                            s,
                            e,
                            (idx + 1) * 10,
                        )
                logger.info(
                    f"{len(blocks_original)} segments originaux sauvegardes en DB (fallback, pas de traduction)",
                    extra=log_extra,
                )
                return StepResult(
                    data={"segments_saved": len(blocks_original), "fallback": True}
                )
            except Exception as e2:
                logger.warning(
                    "Echec fallback sauvegarde segments DB",
                    extra={"error": str(e2), **log_extra},
                )
                return StepResult(data={"segments_saved": 0})
    except Exception as e:
        logger.warning(
            "Echec sauvegarde segments DB",
            extra={"error": str(e), **log_extra},
        )
        return StepResult(data={"segments_saved": 0})