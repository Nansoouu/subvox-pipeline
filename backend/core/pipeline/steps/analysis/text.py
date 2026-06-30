"""
Étape text_analysis — Analyse textuelle du transcript.
"""

from __future__ import annotations

from core.logging_setup import get_logger
from core.pipeline.steps._types import StepResult

logger = get_logger(__name__)


async def step_text_analysis(
    job_id: str,
    transcript: str = "",
    title: str = "",
    description: str = "",
) -> StepResult:
    """
    Étape 3 bis — Analyse textuelle du transcript via OpenRouter DeepSeek V3.1.
    Extrait thèmes, tonalité, highlights, mots-clés, entités nommées.
    """
    from core.pipeline.text_analysis import TextAnalysisStep

    log_extra = {"job_id": job_id[:8], "transcript_len": len(transcript)}
    logger.info("Démarrage text_analysis", extra=log_extra)

    if not transcript:
        logger.warning("text_analysis: transcript vide — skip", extra=log_extra)
        return StepResult(
            success=True,
            data={"themes": [], "tone": "neutral", "highlights": []},
        )

    try:
        step = TextAnalysisStep()
        result = await step.analyze({
            "transcript": transcript,
            "title": title,
            "description": description,
            "user_id": f"job_{job_id}",
        })
        logger.info(
            "TextAnalysis OK",
            extra={
                "themes": len(result.get("themes", [])),
                "highlights": len(result.get("highlights", [])),
                **log_extra,
            },
        )
        return StepResult(success=True, data=result)
    except Exception as exc:
        logger.error(
            "TextAnalysis échouée",
            extra={"error": str(exc), **log_extra},
        )
        return StepResult(
            success=False,
            data={"themes": [], "tone": "neutral"},
            error=str(exc),
        )