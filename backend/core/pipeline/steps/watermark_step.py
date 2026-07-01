"""
Étape 9 : Génération du watermark (custom user text only).
"""

from __future__ import annotations


from core.logging_setup import get_logger
from core.pipeline.steps._types import StepResult

logger = get_logger(__name__)


async def step_watermark(
    job_id: str,
    user_id: str = "anonymous",
) -> StepResult:
    """
    Ne genere un watermark que si l'utilisateur a un texte personnalise en DB.
    Sinon retourne StepResult(data={"watermark_generated": False}).
    """
    if not user_id or user_id == "anonymous":
        return StepResult(data={"watermark_generated": False})

    # Chercher le texte personnalise en DB
    wm_text = ""
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

    if not wm_text:
        return StepResult(data={"watermark_generated": False})

    # Si on arrive ici, l'utilisateur a un texte perso
    # Le watermark sera genere via drawtext dans l'etape burn
    # On stocke juste l'info pour l'etape suivante
    from core.config import settings

    logger.info(
        f"Watermark personnalise actif pour user={user_id} text={wm_text!r}",
        extra={"job_id": job_id},
    )
    return StepResult(
        data={
            "watermark_generated": True,
            "watermark_text": wm_text,
            "watermark_mode": settings.WATERMARK_MODE,
            "watermark_opacity": settings.WATERMARK_SPORADIC_OPACITY,
        },
    )
