"""
Étape fusion — Fusion des analyses en résumé global enrichi.
"""

from __future__ import annotations

from core.logging_setup import get_logger
from core.pipeline.steps._types import StepResult

logger = get_logger(__name__)


async def step_fusion(
    job_id: str,
    meta_analysis: dict | None = None,
    text_analysis: dict | None = None,
    visual_analysis: dict | None = None,
    anonymization: dict | None = None,
    speakers: dict | None = None,
) -> StepResult:
    """
    Étape finale — Fusion des 5 analyses en résumé global enrichi.
    Combine meta + text + visual + anonymization + speakers via
    DeepSeek V3.1 pour produire un résumé, des tags SEO et un score qualité.
    """
    from core.pipeline.fusion import FusionStep

    log_extra = {"job_id": job_id[:8]}
    logger.info("Démarrage fusion", extra=log_extra)

    try:
        step = FusionStep()
        result = await step.analyze({
            "meta_analysis": meta_analysis or {},
            "text_analysis": text_analysis or {},
            "visual_analysis": visual_analysis or {},
            "anonymization": anonymization or {},
            "speakers": speakers or {},
            "job_id": job_id,
        })
        logger.info(
            "Fusion OK",
            extra={
                "score": result.get("quality_score", 0),
                "tags": len(result.get("tags", [])),
                "missing": result.get("missing_analyses", []),
                **log_extra,
            },
        )
        return StepResult(success=True, data=result)
    except Exception as exc:
        logger.error(
            "Fusion échouée",
            extra={"error": str(exc), **log_extra},
        )
        return StepResult(
            success=False,
            data={
                "global_summary": "Fusion échouée.",
                "tags": [], "quality_score": 0.0,
            },
            error=str(exc),
        )