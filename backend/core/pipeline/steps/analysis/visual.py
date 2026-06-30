"""
Étape visual_analysis — Analyse visuelle par extraction de frames.
"""

from __future__ import annotations

from core.logging_setup import get_logger
from core.pipeline.steps._types import StepResult

logger = get_logger(__name__)


async def step_visual_analysis(
    job_id: str,
    video_path: str = "",
    duration_s: float = 0.0,
    srt_timestamps: list[float] | None = None,
) -> StepResult:
    """
    Étape d'analyse visuelle — extraction de frames + Qwen3-VL.

    Optimisé (2026-05-08) :
      - Accepte `srt_timestamps` optionnel pour cibler les frames
        aux timestamps des sous-titres plutôt qu'un échantillonnage uniforme.
      - Si srt_timestamps est fourni, l'analyse se concentre sur ces moments-clés.
    """
    from core.pipeline.visual_analysis import VisualAnalysisStep

    log_extra = {"job_id": job_id[:8], "duration_s": duration_s}
    if srt_timestamps:
        log_extra["srt_timestamps_count"] = len(srt_timestamps)

    logger.info("Démarrage visual_analysis", extra=log_extra)

    if not video_path:
        logger.warning("visual_analysis: video_path vide — skip", extra=log_extra)
        return StepResult(
            success=True,
            data={"scene_count": 0, "scenes": [], "global_faces_count": 0},
        )

    try:
        step = VisualAnalysisStep()
        params = {
            "video_path": video_path,
            "duration_s": duration_s,
            "user_id": f"job_{job_id}",
        }
        if srt_timestamps:
            params["srt_timestamps"] = srt_timestamps

        result = await step.analyze(params)
        logger.info(
            "VisualAnalysis OK",
            extra={
                "scenes": result.get("scene_count", 0),
                "faces": result.get("global_faces_count", 0),
                "frames": result.get("frames_analyzed", 0),
                "srt_timestamps_used": len(srt_timestamps) if srt_timestamps else 0,
                **log_extra,
            },
        )
        return StepResult(success=True, data=result)
    except Exception as exc:
        logger.error(
            "VisualAnalysis échouée",
            extra={"error": str(exc), **log_extra},
        )
        return StepResult(
            success=False,
            data={"scene_count": 0, "scenes": []},
            error=str(exc),
        )
