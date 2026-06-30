"""
Étape anonymization — Floutage adaptatif visages/plaques.
"""

from __future__ import annotations

from core.logging_setup import get_logger
from core.pipeline.steps._types import StepResult

logger = get_logger(__name__)


async def step_anonymization(
    job_id: str,
    video_path: str = "",
    anonymization_config: dict | None = None,
    duration_s: float = 0.0,
) -> StepResult:
    """
    Étape 4 ter — Floutage adaptatif visages/plaques via YOLOv8 + OpenCV.
    """
    from core.pipeline.anonymization import AnonymizationStep

    log_extra = {"job_id": job_id[:8]}
    logger.info("Démarrage anonymization", extra=log_extra)

    if not video_path:
        logger.warning("anonymization: video_path vide — skip", extra=log_extra)
        return StepResult(
            success=True,
            data={
                "faces_detected": 0, "faces_blurred": 0,
                "plates_detected": 0, "plates_blurred": 0,
                "mode": "skipped",
            },
        )

    try:
        step = AnonymizationStep()
        result = await step.analyze({
            "video_path": video_path,
            "anonymization_config": anonymization_config or {"faces": True, "plates": True},
            "duration_s": duration_s,
            "job_id": job_id,
        })
        logger.info(
            "Anonymization OK",
            extra={
                "faces": result.get("faces_detected", 0),
                "mode": result.get("mode", "?"),
                **log_extra,
            },
        )
        return StepResult(success=True, data=result)
    except Exception as exc:
        logger.error(
            "Anonymization échouée",
            extra={"error": str(exc), **log_extra},
        )
        return StepResult(
            success=False,
            data={
                "faces_detected": 0, "faces_blurred": 0,
                "plates_detected": 0, "plates_blurred": 0,
                "mode": "error",
            },
            error=str(exc),
        )