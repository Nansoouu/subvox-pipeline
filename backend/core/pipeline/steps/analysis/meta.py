"""
Étape meta_analysis — Analyse des métadonnées vidéo.
"""

from __future__ import annotations

from core.logging_setup import get_logger
from core.pipeline.steps._types import StepResult

logger = get_logger(__name__)


async def step_meta_analysis(
    job_id: str,
    video_title: str = "",
    video_description: str = "",
    duration_s: float = 0.0,
) -> StepResult:
    """
    Étape 1 bis — Analyse des métadonnées vidéo via OpenRouter DeepSeek V3.1.
    Détermine la catégorie, le type de contenu, la langue probable et
    les recommandations d'anonymisation.
    """
    from core.pipeline.meta_analysis import MetaAnalysisStep

    log_extra = {"job_id": job_id[:8]}
    logger.info("Démarrage meta_analysis", extra=log_extra)

    try:
        step = MetaAnalysisStep()
        result = await step.analyze({
            "title": video_title,
            "description": video_description,
            "duration_s": duration_s,
            "user_id": f"job_{job_id}",
        })
        logger.info(
            "MetaAnalysis OK",
            extra={"category": result.get("category", "?"), **log_extra},
        )
        return StepResult(success=True, data=result)
    except Exception as exc:
        logger.error(
            "MetaAnalysis échouée",
            extra={"error": str(exc), **log_extra},
        )
        return StepResult(
            success=False,
            data={"category": "other"},
            error=str(exc),
        )