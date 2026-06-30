"""
Étape speaker_analysis — Diarisation des locuteurs.
"""

from __future__ import annotations

from core.logging_setup import get_logger
from core.pipeline.steps._types import StepResult

logger = get_logger(__name__)


async def step_speaker_analysis(
    job_id: str,
    video_path: str = "",
    duration_s: float = 0.0,
) -> StepResult:
    """
    Étape 4 quater — Diarisation des locuteurs via Pyannote 3.1.
    """
    from core.pipeline.speaker_analysis import SpeakerAnalysisStep

    log_extra = {"job_id": job_id[:8]}
    logger.info("Démarrage speaker_analysis", extra=log_extra)

    if not video_path:
        logger.warning("speaker_analysis: video_path vide — skip", extra=log_extra)
        return StepResult(
            success=True,
            data={"speakers": [], "total_speakers": 0, "total_segments": 0},
        )

    try:
        step = SpeakerAnalysisStep()
        result = await step.analyze({
            "video_path": video_path,
            "duration_s": duration_s,
            "job_id": job_id,
        })
        logger.info(
            "SpeakerAnalysis OK",
            extra={
                "speakers": result.get("total_speakers", 0),
                "mode": result.get("mode", "?"),
                **log_extra,
            },
        )
        return StepResult(success=True, data=result)
    except Exception as exc:
        logger.error(
            "SpeakerAnalysis échouée",
            extra={"error": str(exc), **log_extra},
        )
        return StepResult(
            success=False,
            data={"speakers": [], "total_speakers": 0},
            error=str(exc),
        )