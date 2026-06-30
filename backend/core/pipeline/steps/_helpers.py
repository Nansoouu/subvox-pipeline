"""
Helpers partagés pour les étapes du pipeline.
"""

from __future__ import annotations

from pathlib import Path

from core.config import settings


def _get_tmp(job_id: str) -> Path:
    return Path(settings.LOCAL_TEMP_DIR) / str(job_id)


def _parse_ffmpeg_progress_line(line: str) -> dict:
    """Parse a single line from ffmpeg -progress pipe:1 output."""
    parts = line.strip().split("=", 1)
    if len(parts) == 2:
        return {parts[0].strip(): parts[1].strip()}
    return {}