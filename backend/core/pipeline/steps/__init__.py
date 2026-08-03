"""
Package steps — Étapes du pipeline extraites en fichiers autonomes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import os


@dataclass
class StepResult:
    success: bool = True
    data: dict[str, Any] | None = None
    error: str | None = None
    skipped: bool = False
    files: dict[str, str] | None = None


PROCESSING_DIR = Path("/tmp/subvox-processing")


def _get_tmp(job_id: str) -> Path:
    p = PROCESSING_DIR / job_id
    p.mkdir(parents=True, exist_ok=True)
    return p


def _parse_ffmpeg_progress_line(line: str) -> dict[str, float]:
    """Parse une ligne du log ffmpeg (format 'frame=xxx fps=xxx ...')."""
    result: dict[str, float] = {}
    for part in line.strip().split():
        if "=" in part:
            k, v = part.split("=", 1)
            try:
                result[k] = float(v)
            except ValueError:
                result[k] = 0.0
    return result


from core.pipeline.steps.download import step_download
from core.pipeline.steps.transcribe import step_transcribe
from core.pipeline.steps.filter import step_filter
from core.pipeline.steps.summary import step_summary
from core.pipeline.steps.translate import step_translate
from core.pipeline.steps.segments import step_segments_save
from core.pipeline.steps.subtitles import step_ass_generation, step_vtt_export, _srt_content_to_vtt
from core.pipeline.steps.watermark_step import step_watermark
from core.pipeline.steps.burn import step_burn
from core.pipeline.steps.lang_metadata import translate_all_metadata, update_job_title_per_lang
from core.pipeline.steps.analysis import (
    step_meta_analysis,
    step_text_analysis,
    step_visual_analysis,
    step_anonymization,
    step_speaker_analysis,
    step_fusion,
)

__all__ = [
    "StepResult",
    "_get_tmp",
    "_parse_ffmpeg_progress_line",
    "step_download",
    "step_transcribe",
    "step_filter",
    "step_summary",
    "step_translate",
    "step_segments_save",
    "step_ass_generation",
    "step_vtt_export",
    "_srt_content_to_vtt",
    "step_watermark",
    "step_burn",
    "translate_all_metadata",
    "update_job_title_per_lang",
    "step_meta_analysis",
    "step_text_analysis",
    "step_visual_analysis",
    "step_anonymization",
    "step_speaker_analysis",
    "step_fusion",
]
