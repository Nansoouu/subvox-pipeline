"""
Étape 9 : Génération du watermark PNG.
"""

from __future__ import annotations


from core.config import settings
from core.logging_setup import get_logger
from core.pipeline.ffmpeg import _get_video_dims
from core.pipeline.watermark import _generate_watermark_png
from core.pipeline.steps._helpers import _get_tmp
from core.pipeline.steps._types import StepResult

logger = get_logger(__name__)


async def step_watermark(
    job_id: str,
    user_id: str = "anonymous",
) -> StepResult:
    """
    Genere le watermark PNG (badge design fixe par defaut).
    Supporte le texte personnalise par utilisateur.
    """
    tmp = _get_tmp(job_id)
    source_path = tmp / "source.mp4"
    wm_path = tmp / "watermark.png"

    if not source_path.exists():
        return StepResult(data={"watermark_generated": False})

    try:
        vid_w, vid_h = _get_video_dims(source_path)
        wm_text = ""
        if user_id and user_id != "anonymous":
            try:
                from core.db import direct_connect as _direct

                async with _direct() as conn:
                    row = await conn.fetchrow(
                        "SELECT watermark_text, watermark_paid "
                        "FROM subscriptions WHERE user_id=$1",
                        str(user_id),
                    )
                if row and row["watermark_paid"] and row["watermark_text"]:
                    wm_text = row["watermark_text"]
                    logger.info(
                        "Watermark personnalise utilisateur",
                        extra={"job_id": job_id},
                    )
            except Exception as exc:
                logger.warning(
                    "Impossible de lire le watermark utilisateur",
                    extra={"error": str(exc), "job_id": job_id},
                )
        wm_bytes = _generate_watermark_png(
            vid_w,
            vid_h,
            text=wm_text,
            mode=settings.WATERMARK_MODE,
            position=settings.WATERMARK_POSITION,
            bg_opacity=settings.WATERMARK_OPACITY,
        )
        if wm_bytes:
            wm_path.write_bytes(wm_bytes)
            logger.info(
                f"Watermark PNG genere ({vid_w}x{vid_h}) mode={settings.WATERMARK_MODE}",
                extra={"job_id": job_id},
            )
            return StepResult(
                files={"watermark_png": str(wm_path)},
                data={"watermark_generated": True},
            )
    except Exception as e:
        logger.warning(
            "Watermark PNG ignore", extra={"error": str(e), "job_id": job_id}
        )

    return StepResult(data={"watermark_generated": False})