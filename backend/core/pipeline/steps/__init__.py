"""
Package steps — Étapes du pipeline extraites en fichiers autonomes.

Ce fichier réexporte toutes les fonctions publiques pour la rétrocompatibilité.
Tous les imports existants (`from core.pipeline.steps import step_download`) continuent
de fonctionner via le proxy steps.py qui fait `from core.pipeline.steps import *`.
"""

from __future__ import annotations

from core.pipeline.steps._types import StepResult
from core.pipeline.steps._helpers import _get_tmp, _parse_ffmpeg_progress_line
from core.pipeline.steps.download import step_download
from core.pipeline.steps.transcribe import step_transcribe
from core.pipeline.steps.filter import step_filter
from core.pipeline.steps.summary import step_summary
from core.pipeline.steps.translate import step_translate
from core.pipeline.steps.segments import step_segments_save
from core.pipeline.steps.subtitles import step_ass_generation, step_vtt_export, _srt_content_to_vtt
from core.pipeline.steps.watermark_step import step_watermark
from core.pipeline.steps.burn import step_burn
from core.pipeline.steps.upload import step_upload
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
    "step_upload",
    "step_meta_analysis",
    "step_text_analysis",
    "step_visual_analysis",
    "step_anonymization",
    "step_speaker_analysis",
    "step_fusion",
]