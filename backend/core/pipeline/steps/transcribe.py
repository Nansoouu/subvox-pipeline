"""
Étape 2 : Transcription Groq Whisper.
"""

from __future__ import annotations

from pathlib import Path

from core.logging_setup import get_logger
from core.pipeline.groq import _transcribe_via_groq
from core.pipeline.srt import _parse_srt
from core.pipeline.steps._helpers import _get_tmp
from core.pipeline.steps._types import StepResult

logger = get_logger(__name__)


async def step_transcribe(
    job_id: str,
    groq_api_key: str = "",
) -> StepResult:
    """
    Transcrit la vidéo via Groq Whisper.
    Produit transcript.srt et transcript.txt.
    """
    tmp = _get_tmp(job_id)
    srt_path = tmp / "transcript.srt"
    txt_path = tmp / "transcript.txt"

    # Récupère la source
    source_mp4_path = str(tmp / "source.mp4")
    if not Path(source_mp4_path).exists():
        raise RuntimeError("Fichier source introuvable pour transcription")

    whisper_result = _transcribe_via_groq(
        Path(source_mp4_path), srt_path, txt_path, groq_api_key
    )
    if not whisper_result:
        raise RuntimeError("Transcription Groq echouee")

    transcript_tx = whisper_result.get("text", "")
    source_lang = whisper_result.get("language", "en")

    srt_raw = ""
    total_segments = 0
    if srt_path.exists():
        srt_raw = srt_path.read_text(encoding="utf-8")
        total_segments = len(_parse_srt(srt_raw))

    return StepResult(
        data={
            "raw_srt": srt_raw,
            "text": transcript_tx,
            "source_lang": source_lang,
            "language": source_lang,
            "model": whisper_result.get("model", "whisper-large-v3-turbo"),
            "segments": whisper_result.get("segments", []),
            "total_segments": total_segments,
        },
        files={"srt_path": str(srt_path), "txt_path": str(txt_path)},
    )