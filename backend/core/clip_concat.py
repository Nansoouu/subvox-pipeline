"""
backend/core/clip_concat.py — Concaténation de clips vidéo avec FFmpeg filter_complex
Normalisation des codecs/résolutions pour compatibilité — Subvox
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional

from core.logging_setup import get_logger

logger = get_logger(__name__)


def _ffmpeg_path() -> str:
    """Retourne le chemin de ffmpeg."""
    candidates = ["/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg", "ffmpeg"]
    for c in candidates:
        try:
            subprocess.run([c, "-version"], capture_output=True, check=True, timeout=5)
            return c
        except Exception:
            continue
    return "ffmpeg"


def normalize_video(input_path: Path, output_path: Path) -> bool:
    """
    Normalise une vidéo pour la concaténation :
      - Résolution : 1280x720 (16:9)
      - Codec : H.264, yuv420p
      - FPS : 30
      - Audio : AAC, 128k
    """
    ffmpeg = _ffmpeg_path()

    cmd = [
        ffmpeg,
        "-y",
        "-nostdin",
        "-i",
        str(input_path),
        "-vf",
        "scale=1280:720:force_original_aspect_ratio=decrease,"
        "pad=1280:720:(ow-iw)/2:(oh-ih)/2:black,"
        "format=yuv420p",
        "-r",
        "30",
        "-c:v",
        "libx264",
        "-crf",
        "23",
        "-preset",
        "fast",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-movflags",
        "+faststart",
        str(output_path),
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if (
            result.returncode == 0
            and output_path.exists()
            and output_path.stat().st_size > 0
        ):
            logger.info(f"Normalisé {input_path.name} → {output_path.name}")
            return True
        logger.error(f"Normalisation échouée: {result.stderr[-300:]}")
        return False
    except Exception as e:
        logger.error(f"Erreur normalisation: {e}")
        return False


def concat_clips(
    clip_paths: List[Path],
    output_path: Path,
    normalize: bool = True,
) -> bool:
    """
    Concatène plusieurs clips vidéo en utilisant FFmpeg filter_complex.
    """
    if not clip_paths:
        logger.error("Aucun clip à concaténer")
        return False

    if len(clip_paths) == 1:
        try:
            import shutil

            shutil.copy2(clip_paths[0], output_path)
            logger.info(f"Copié unique clip → {output_path.name}")
            return True
        except Exception as e:
            logger.error(f"Erreur copie: {e}")
            return False

    ffmpeg = _ffmpeg_path()

    if normalize:
        with tempfile.TemporaryDirectory() as tmpdir:
            normalized_paths = []
            for i, clip_path in enumerate(clip_paths):
                if not clip_path.exists():
                    logger.error(f"Clip introuvable: {clip_path}")
                    return False
                normalized = Path(tmpdir) / f"norm_{i}.mp4"
                if not normalize_video(clip_path, normalized):
                    logger.error(f"Échec normalisation: {clip_path.name}")
                    return False
                normalized_paths.append(normalized)

            list_file = Path(tmpdir) / "list.txt"
            list_content = "\n".join(
                [f"file '{p.absolute()}'" for p in normalized_paths]
            )
            list_file.write_text(list_content, encoding="utf-8")

            cmd = [
                ffmpeg,
                "-y",
                "-nostdin",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(list_file),
                "-c",
                "copy",
                "-movflags",
                "+faststart",
                str(output_path),
            ]
    else:
        inputs = []
        filter_parts = []
        for i in range(len(clip_paths)):
            inputs.extend(["-i", str(clip_paths[i])])
            filter_parts.extend([f"[{i}:v]", f"[{i}:a]"])
        filter_complex = (
            "".join(filter_parts) + f"concat=n={len(clip_paths)}:v=1:a=1 [v] [a]"
        )
        cmd = [
            ffmpeg,
            "-y",
            "-nostdin",
            *inputs,
            "-filter_complex",
            filter_complex,
            "-map",
            "[v]",
            "-map",
            "[a]",
            "-c:v",
            "libx264",
            "-crf",
            "23",
            "-preset",
            "fast",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-movflags",
            "+faststart",
            str(output_path),
        ]

    try:
        logger.info(f"Concaténation de {len(clip_paths)} clips...")
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=max(600, len(clip_paths) * 60)
        )
        if (
            result.returncode == 0
            and output_path.exists()
            and output_path.stat().st_size > 0
        ):
            duration = output_path.stat().st_size / (1024 * 1024)
            logger.info(
                f"Concaténation réussie: {output_path.name} ({duration:.1f} MB)"
            )
            return True
        logger.error(
            f"Concaténation échouée: code={result.returncode}",
            extra={"stderr": result.stderr[-500:] if result.stderr else ""},
        )
        return False
    except subprocess.TimeoutExpired:
        logger.error(f"Timeout concaténation ({len(clip_paths)} clips)")
        return False
    except Exception as e:
        logger.error(f"Erreur concaténation: {e}")
        return False


def estimate_concat_duration(clip_paths: List[Path]) -> Optional[float]:
    """Estime la durée totale de la concaténation."""
    total = 0.0
    ffprobe = _ffmpeg_path().replace("ffmpeg", "ffprobe")

    for clip in clip_paths:
        if not clip.exists():
            logger.warning(f"Clip introuvable pour estimation: {clip}")
            continue

        cmd = [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(clip),
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                total += float(result.stdout.strip())
            else:
                logger.warning(f"Impossible d'estimer durée {clip.name}")
        except Exception:
            logger.warning(f"Erreur estimation durée {clip.name}")

    return total if total > 0 else None
