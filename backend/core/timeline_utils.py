"""
core/timeline_utils.py — Utilitaires timeline (SRT, reorder, segments) — Subvox
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Optional

from core.logging_setup import get_logger

logger = get_logger(__name__)


def _ffmpeg_path() -> str:
    import subprocess

    candidates = ["/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg", "ffmpeg"]
    for c in candidates:
        try:
            subprocess.run([c, "-version"], capture_output=True, check=True, timeout=5)
            return c
        except Exception:
            continue
    return "ffmpeg"


async def get_next_order_position(job_id: uuid.UUID) -> int:
    """Retourne le prochain ordre disponible pour un job."""
    from core.db import get_conn

    async with get_conn() as conn:
        row = await conn.fetchval(
            "SELECT COALESCE(MAX(custom_order), 0) + 10 FROM transcription_segments WHERE job_id=$1",
            job_id,
        )
    return row or 10


async def reorder_segments(job_id: uuid.UUID) -> bool:
    """Réordonne les segments d'un job après split/merge/delete."""
    from core.db import get_conn

    try:
        async with get_conn() as conn:
            await conn.execute(
                """
                UPDATE transcription_segments SET custom_order = sub.new_order
                FROM (
                    SELECT id, ROW_NUMBER() OVER (ORDER BY custom_order NULLS LAST, start_time) * 10 as new_order
                    FROM transcription_segments WHERE job_id=$1
                ) sub
                WHERE transcription_segments.id = sub.id AND transcription_segments.job_id = $1
                """,
                job_id,
            )
        logger.info(f"Segments réordonnés pour job {job_id}")
        return True
    except Exception as e:
        logger.error(f"Erreur reorder_segments({job_id}): {e}")
        return False


async def get_segments_with_order(job_id: uuid.UUID) -> list[dict]:
    """Retourne les segments triés par custom_order."""
    from core.db import get_conn

    async with get_conn() as conn:
        rows = await conn.fetch(
            """SELECT id, start_time, end_time, original_text, translated_text, style
               FROM transcription_segments WHERE job_id=$1
               ORDER BY custom_order NULLS LAST, start_time""",
            job_id,
        )
    return [dict(r) for r in rows]


async def get_original_srt_content(job_id: uuid.UUID) -> Optional[str]:
    """Génère un SRT à partir des segments originaux."""
    from core.timeline_utils import get_segments_with_order

    segments = await get_segments_with_order(job_id)
    if not segments:
        return None
    return generate_corrected_srt(segments, mode="original")


async def get_translated_srt_content(job_id: uuid.UUID) -> Optional[str]:
    """Génère un SRT à partir des segments traduits."""
    from core.timeline_utils import get_segments_with_order

    segments = await get_segments_with_order(job_id)
    if not segments:
        return None
    return generate_corrected_srt(segments, mode="translated")


def generate_corrected_srt(
    segments: list[dict],
    mode: str = "original",
) -> str:
    """Génère un fichier SRT à partir des segments."""

    def _to_srt_time(seconds: float) -> str:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        ms = int((seconds - int(seconds)) * 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    text_key = "original_text" if mode == "original" else "translated_text"
    lines = []
    for idx, seg in enumerate(segments, 1):
        text = seg.get(text_key, "").strip() or seg.get("original_text", "").strip()
        if not text:
            continue
        start = float(seg["start_time"])
        end = float(seg["end_time"])
        lines.append(f"{idx}\n{_to_srt_time(start)} --> {_to_srt_time(end)}\n{text}\n")

    return "\n".join(lines)


def validate_srt_order(srt_content: str) -> bool:
    """Valide que l'ordre des timestamps SRT est cohérent."""
    import re

    if not srt_content.strip():
        return True
    timestamps = re.findall(
        r"(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})", srt_content
    )
    last_end = 0.0
    for start_str, end_str in timestamps:

        def _parse(ts):
            h, m, s_ms = ts.split(":")
            s, ms = s_ms.split(",")
            return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000

        start = _parse(start_str)
        end = _parse(end_str)
        if start < last_end:
            logger.warning(f"Trou dans l'ordre SRT: {start} < {last_end}")
        last_end = end
    return True
