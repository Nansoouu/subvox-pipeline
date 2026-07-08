"""
Étape 10 : Burn des sous-titres sur la vidéo.
Contient également les helpers _burn_ass et _burn_ass_with_progress
(déplacés depuis runner.py lors du refactoring).
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Optional

from core.logging_setup import get_logger
from core.pipeline.ffmpeg import (
    _ffmpeg_path,
    _get_video_dims,
    _get_video_duration,
    _get_video_frames,
    _get_ffmpeg_encoding_options,
    get_libass_ok,
)
from core.pipeline.pillow import _burn_subtitles_pillow
from core.pipeline.watermark import (
    _compute_sporadic_timecodes,
    _build_sporadic_drawtext_filters,
)
from core.pipeline.steps._helpers import _get_tmp
from core.pipeline.steps._types import StepResult
from core.config import settings

logger = get_logger(__name__)


# ─── Helpers FFmpeg (importés depuis _helpers, utilisés par step_burn) ──────


def _burn_ass_with_progress(
    video: Path,
    ass_path: Path,
    output: Path,
    job_id: str = "",
    wm_path: Optional[Path] = None,
    on_progress: Optional[callable] = None,
) -> bool:
    """
    Burn ASS via filtre libass avec suivi de progression via -progress pipe:1.
    Optionnellement avec watermark.
    Mono-passe : combine ASS + overlay watermark en un seul appel FFmpeg.
    Appelle on_progress(pct) périodiquement si fourni.
    """
    ffmpeg = _ffmpeg_path()
    vid_w, vid_h = _get_video_dims(video)
    _get_video_frames(video)
    wm_exists = wm_path and wm_path.exists()

    if settings.WATERMARK_SPORADIC_ENABLED and settings.WATERMARK_TEXT:
        duration_s = _get_video_duration(video) or 60

        timecodes = _compute_sporadic_timecodes(
            duration_s,
            interval=settings.WATERMARK_SPORADIC_INTERVAL,
            text_duration=settings.WATERMARK_SPORADIC_DURATION,
        )
        drawtext_filters, last_label = _build_sporadic_drawtext_filters(
            vid_w, vid_h,
            text=settings.WATERMARK_TEXT,
            timecodes=timecodes,
            opacity=settings.WATERMARK_SPORADIC_OPACITY,
        )

        # Chain: ASS → drawtext overlay sur la même base
        filter_complex = (
            f"[0:v]ass={ass_path}[base];"
            f"{drawtext_filters}"
        )

        cmd = (
            [
                ffmpeg,
                "-y",
                "-i",
                str(video),
                "-filter_complex",
                filter_complex,
                "-map",
                f"[{last_label}]",
                "-map",
                "0:a",
                "-c:a",
                "copy",
            ]
            + _get_ffmpeg_encoding_options()
            + ["-progress", "pipe:1"]
            + [str(output)]
        )
    else:
        cmd = (
            [
                ffmpeg,
                "-y",
                "-i",
                str(video),
                "-vf",
                f"ass={ass_path}",
                "-c:a",
                "copy",
            ]
            + _get_ffmpeg_encoding_options()
            + ["-progress", "pipe:1"]
            + [str(output)]
        )

    logger.info(f"FFMPEG BURN CMD: {' '.join(str(c) for c in cmd)}")
    try:
        # Use run() to avoid deadlock with Popen + pipe (ffmpeg writes to pipe:1)
        r = subprocess.run(cmd, capture_output=True, timeout=7200, text=True)
        if r.returncode != 0 or not output.exists():
            logger.error(
                f"ASS burn echoue: {video.name} (rc={r.returncode}) stderr={r.stderr[:500] if r.stderr else ''}",
            )
            return _burn_ass(video, ass_path, output, wm_path, job_id)
    except Exception as e:
        logger.error(f"FFmpeg burn exception: {e}")
        return _burn_ass(video, ass_path, output, wm_path, job_id)

    if output.exists():
        logger.info(
            "ASS burn RESULT: "
            f"video={video.name} "
            f"size={output.stat().st_size // 1024}KB "
            f"wm={'YES' if wm_exists else 'NO'} "
            f"mode={'libass+progress' if on_progress else 'libass'}"
        )

        # Log les premieres lignes du fichier ASS pour vérifier les styles/couleurs
        if ass_path and ass_path.exists():
            ass_preview = ass_path.read_text(encoding="utf-8").split("\n")[:30]
            style_line = [l for l in ass_preview if l.startswith("Style:")]
            sample_dialogue = [l for l in ass_preview if l.startswith("Dialogue:")]
            logger.info(
                "ASS debug preview — "
                f"style={style_line[0] if style_line else 'N/A'} | "
                f"dialogue={sample_dialogue[0] if sample_dialogue else 'N/A'} | "
                f"total_lines={len(ass_preview)}"
            )

        return True
    return False


def _burn_ass(
    video: Path,
    ass_path: Path,
    output: Path,
    wm_path: Optional[Path] = None,
    job_id: str = "",
) -> bool:
    """Burn ASS via filtre libass, optionnellement avec watermark (version sans progress).
    Mono-passe : combine ASS + overlay watermark en un seul appel FFmpeg."""
    ffmpeg = _ffmpeg_path()
    vid_w, vid_h = _get_video_dims(video)
    wm_exists = wm_path and wm_path.exists()

    if settings.WATERMARK_SPORADIC_ENABLED and settings.WATERMARK_TEXT:
        duration_s = _get_video_duration(video) or 60

        timecodes = _compute_sporadic_timecodes(
            duration_s,
            interval=settings.WATERMARK_SPORADIC_INTERVAL,
            text_duration=settings.WATERMARK_SPORADIC_DURATION,
        )
        drawtext_filters, last_label = _build_sporadic_drawtext_filters(
            vid_w, vid_h,
            text=settings.WATERMARK_TEXT,
            timecodes=timecodes,
            opacity=settings.WATERMARK_SPORADIC_OPACITY,
        )

        # Chain: ASS → drawtext overlay sur la même base
        filter_complex = (
            f"[0:v]ass={ass_path}[base];"
            f"{drawtext_filters}"
        )

        cmd = (
            [
                ffmpeg,
                "-y",
                "-i",
                str(video),
                "-filter_complex",
                filter_complex,
                "-map",
                f"[{last_label}]",
                "-map",
                "0:a",
                "-c:a",
                "copy",
            ]
            + _get_ffmpeg_encoding_options()
            + [str(output)]
        )
    else:
        cmd = (
            [
                ffmpeg,
                "-y",
                "-i",
                str(video),
                "-vf",
                f"ass={ass_path}",
                "-c:a",
                "copy",
            ]
            + _get_ffmpeg_encoding_options()
            + [str(output)]
        )

    r = subprocess.run(cmd, capture_output=True, timeout=7200)
    if r.returncode != 0 or not output.exists():
        logger.error(
            f"ASS burn echoue: {video.name} (rc={r.returncode}) stderr={r.stderr[:500] if r.stderr else ''}",
        )
        return False

    if settings.WATERMARK_SPORADIC_ENABLED and settings.WATERMARK_TEXT:
        n_timecodes = len(timecodes) if drawtext_filters else 0
        logger.info(
            "Watermark texte sporadique ajoute",
            extra={
                "video": video.name,
                "job_id": job_id,
                "n_apparitions": n_timecodes,
                "interval": settings.WATERMARK_SPORADIC_INTERVAL,
                "duration": settings.WATERMARK_SPORADIC_DURATION,
            },
        )

    if output.exists():
        logger.info(
            f"ASS burn OK: {output.name} ({output.stat().st_size // 1024} KB)",
            extra={"job_id": job_id},
        )
        return True
    return False


# ─── Step principale ────────────────────────────────────────────────────────


async def step_burn(
    job_id: str,
    on_progress: Optional[callable] = None,
    ass_path_override: str = "",
    output_filename: str = "burned.mp4",
) -> StepResult:
    """
    Brûle les sous-titres (ASS) et le watermark sur la vidéo.
    Priorise libass, fallback Pillow.
    """
    log_extra = {"job_id": job_id}
    tmp = _get_tmp(job_id)
    source_path = tmp / "source.mp4"
    burned_mp4 = tmp / output_filename
    ass_path = Path(ass_path_override) if ass_path_override else tmp / "subtitles.ass"
    wm_path = tmp / "watermark.png"

    if not source_path.exists():
        raise RuntimeError("Fichier source introuvable pour burn")

    logger.info("Burn sous-titres + watermark en cours", extra=log_extra)

    burn_success = False
    force_pillow = os.environ.get("SUBTITLE_BURN_MODE", "").lower() == "pillow"
    if force_pillow or not get_libass_ok():
        burn_success = _burn_subtitles_pillow(
            source_path,
            ass_path if ass_path.exists() else (tmp / "transcript.srt"),
            burned_mp4,
            wm_path if wm_path.exists() else None,
        )
    else:
        burn_success = _burn_ass_with_progress(
            source_path,
            ass_path,
            burned_mp4,
            wm_path=wm_path if wm_path.exists() else None,
            job_id=job_id,
            on_progress=on_progress,
        )

    if not burn_success or not burned_mp4.exists():
        raise RuntimeError("Burn sous-titres echoue")

    # Métriques burn
    burn_output_size_mb = round(burned_mp4.stat().st_size / (1024 * 1024), 2)
    burn_total_frames = _get_video_frames(source_path) or 0
    burn_duration_s = _get_video_duration(burned_mp4) or 0.0
    burn_fps_avg = (
        round(burn_total_frames / burn_duration_s, 2) if burn_duration_s > 0 else 0.0
    )
    burn_mode = "pillow" if (force_pillow or not get_libass_ok()) else "libass"

    logger.info(
        f"Burn OK: {burned_mp4.stat().st_size // 1024} KB "
        f"({burn_total_frames} frames {burn_fps_avg}fps {burn_output_size_mb}MB mode={burn_mode})",
        extra=log_extra,
    )

    return StepResult(
        files={"burned_mp4": str(burned_mp4)},
        data={
            "burn_size_kb": burned_mp4.stat().st_size // 1024,
            "burn_mode": burn_mode,
            "burn_total_frames": burn_total_frames,
            "burn_duration_s": round(burn_duration_s, 2),
            "burn_output_size_mb": burn_output_size_mb,
            "burn_fps_avg": burn_fps_avg,
        },
    )
