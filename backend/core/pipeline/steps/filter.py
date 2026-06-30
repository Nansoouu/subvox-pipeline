"""
Étape 3 : Filtre des hallucinations (regex + LLM).
"""

from __future__ import annotations

from core.logging_setup import get_logger
from core.pipeline.srt import _parse_srt, _write_srt
from core.pipeline.steps._helpers import _get_tmp
from core.pipeline.steps._types import StepResult

logger = get_logger(__name__)


async def step_filter(
    job_id: str,
    srt_raw: str = "",
    transcript_tx: str = "",
) -> StepResult:
    """
    Filtre les hallucinations (regex + LLM) du SRT brut.
    """
    from core.whisper_hallucination_filter import (
        filter_hallucinations_regex,
        apply_llm_hallucination_filter,
    )

    log_extra = {"job_id": job_id}

    if not srt_raw:
        tmp = _get_tmp(job_id)
        srt_path = tmp / "transcript.srt"
        if srt_path.exists():
            srt_raw = srt_path.read_text(encoding="utf-8")

    blocks = _parse_srt(srt_raw)
    blocks, removed_regex = filter_hallucinations_regex(blocks)
    if removed_regex:
        logger.info(
            f"{removed_regex} hallucination(s) regex supprimee(s)",
            extra=log_extra,
        )
    # Garde-fou : si tous les segments ont été filtrés, on garde l'original
    # (arrive avec les langues CJK où la détection CJK n'a pas suffi)
    if not blocks and srt_raw:
        logger.warning(
            "Tous les segments filtres — garde SRT original",
            extra=log_extra,
        )
        blocks = _parse_srt(srt_raw)
        removed_regex = 0

    try:
        removed_llm, _no_audio = await apply_llm_hallucination_filter(
            blocks, transcript_tx
        )
        if _no_audio:
            logger.warning("LLM : aucun contenu audio valide", extra=log_extra)
        elif removed_llm:
            logger.info(
                f"{removed_llm} hallucination(s) LLM supprimee(s)",
                extra=log_extra,
            )
    except Exception as e:
        logger.warning(
            "Filtre hallucination LLM ignore",
            extra={"error": str(e), **log_extra},
        )

    total_post_filter = len(blocks)
    clean_srt = _write_srt(blocks)
    tmp = _get_tmp(job_id)
    srt_path = tmp / "transcript.srt"
    srt_path.write_text(clean_srt, encoding="utf-8")

    return StepResult(
        data={
            "raw_srt": clean_srt,
            "removed_regex": removed_regex,
            "removed_llm": removed_llm if isinstance(removed_llm, int) else 0,
            "total_post_filter": total_post_filter,
        },
        files={"srt_path": str(srt_path)},
    )