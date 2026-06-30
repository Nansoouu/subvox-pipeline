"""
core/clip_extractor.py — Découpe de clips + reformatage 9:16/16:9/1:1 — Studio
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Literal

from core.logging_setup import get_logger

logger = get_logger(__name__)

Format = Literal["9:16", "16:9", "1:1"]


def _ffmpeg_path() -> str:
    candidates = ["/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg", "ffmpeg"]
    for c in candidates:
        try:
            subprocess.run([c, "-version"], capture_output=True, check=True, timeout=5)
            return c
        except Exception:
            continue
    return "ffmpeg"


def _get_ar(aspect: Format) -> tuple[int, int]:
    if aspect == "9:16":
        return 720, 1280
    elif aspect == "1:1":
        return 1080, 1080
    return 1280, 720  # 16:9


def extract_clip(
    source: Path,
    output: Path,
    start_s: float,
    end_s: float,
    target_format: Format = "16:9",
) -> bool:
    """
    Extrait un clip vidéo entre start_s et end_s, au format cible.

    Args:
        source: Chemin de la vidéo source
        output: Chemin de sortie du clip
        start_s: Timecode de début en secondes
        end_s: Timecode de fin en secondes
        target_format: Format cible 9:16, 16:9 ou 1:1

    Returns:
        True si succès, False sinon
    """
    duration = end_s - start_s
    if duration <= 0:
        logger.error(f"Durée invalide: {start_s} → {end_s}")
        return False

    w, h = _get_ar(target_format)
    ffmpeg = _ffmpeg_path()

    cmd = [
        ffmpeg,
        "-y",
        "-ss",
        str(start_s),
        "-i",
        str(source),
        "-t",
        str(duration),
        "-vf",
        f"crop=min(iw\\,ih*{w}/{h}):min(ih\\,iw*{h}/{w}),scale={w}:{h}",
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "20",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-movflags",
        "+faststart",
        str(output),
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, timeout=7200)
        if result.returncode == 0 and output.exists() and output.stat().st_size > 0:
            logger.info(
                f"Clip extrait: {output.name} [{target_format}] {duration:.1f}s"
            )
            return True
        logger.error(
            f"Extraction échouée: code={result.returncode}",
            extra={"stderr": result.stderr[-300:] if result.stderr else ""},
        )
        return False
    except Exception as e:
        logger.error(f"Erreur extraction clip: {e}")
        return False
