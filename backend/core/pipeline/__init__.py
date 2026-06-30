"""
pipeline/__init__.py — Sous-package pipeline découpé en modules — Subvox

Modules :
  - cookies    : _is_valid_cookies_file
  - ffmpeg     : _ffmpeg_path, _has_libass, _get_video_dims, etc.
  - srt        : _parse_srt, _write_srt, _srt_to_ass, etc.
  - groq       : _transcribe_via_groq
  - pillow     : _burn_subtitles_pillow
  - watermark  : _generate_watermark_png
  - runner     : _burn_ass, run_pipeline (alias process_video)
"""

# Init FFmpeg caps au chargement du package
from core.pipeline.ffmpeg import init_ffmpeg_caps

init_ffmpeg_caps()

from core.pipeline.cookies import _is_valid_cookies_file
from core.pipeline.ffmpeg import (
    _ffmpeg_path,
    _has_libass,
    _has_drawtext,
    _get_ffmpeg_encoding_options,
    _get_video_dims,
    _get_video_duration,
    _get_video_fps,
    init_ffmpeg_caps,
    get_libass_ok,
    get_drawtext_ok,
    _LIBASS_OK,
    _DRAWTEXT_OK,
)
from core.pipeline.srt import (
    _parse_srt,
    _write_srt,
    _shift_srt_timing,
    _srt_to_ass,
    _to_srt_time,
    _parse_time_to_seconds,
    _srt_time_to_ass,
    _adjust_duration_based_on_text,
)
from core.pipeline.groq import _transcribe_via_groq
from core.pipeline.pillow import _burn_subtitles_pillow
from core.pipeline.watermark import _generate_watermark_png
from core.pipeline.seo import generate_seo_metadata, save_seo_metadata
from core.pipeline.steps.burn import _burn_ass
from core.pipeline.runner import run_pipeline, process_video

__all__ = [
    "generate_seo_metadata",
    "save_seo_metadata",
    "_is_valid_cookies_file",
    "_ffmpeg_path",
    "_has_libass",
    "_has_drawtext",
    "_get_ffmpeg_encoding_options",
    "_get_video_dims",
    "_get_video_duration",
    "_get_video_fps",
    "init_ffmpeg_caps",
    "get_libass_ok",
    "get_drawtext_ok",
    "_LIBASS_OK",
    "_DRAWTEXT_OK",
    "_parse_srt",
    "_write_srt",
    "_shift_srt_timing",
    "_srt_to_ass",
    "_to_srt_time",
    "_parse_time_to_seconds",
    "_srt_time_to_ass",
    "_adjust_duration_based_on_text",
    "_transcribe_via_groq",
    "_burn_subtitles_pillow",
    "_generate_watermark_png",
    "_burn_ass",
    "run_pipeline",
    "process_video",
    "generate_seo_metadata",
    "save_seo_metadata",
]
