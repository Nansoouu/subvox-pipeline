"""
pipeline/ffmpeg.py — Helpers FFmpeg (paths, caps, options, probes) — Subvox
"""

import subprocess
import re
from pathlib import Path

from core.logging_setup import get_logger

logger = get_logger(__name__)


def _ffmpeg_path() -> str:
    candidates = [
        "/opt/homebrew/bin/ffmpeg",
        "/usr/local/bin/ffmpeg",
        "/usr/bin/ffmpeg",
        "ffmpeg",
    ]
    for c in candidates:
        try:
            subprocess.run([c, "-version"], capture_output=True, check=True, timeout=5)
            return c
        except Exception:
            continue
    logger.warning(
        "Aucun binaire ffmpeg trouve dans le PATH — le pipeline Groq echouera"
    )
    return "ffmpeg"


def _has_libass() -> bool:
    """
    Verifie si le filtre 'ass' est reellement disponible dans ce build FFmpeg.
    """
    try:
        r = subprocess.run(
            [_ffmpeg_path(), "-filters"], capture_output=True, timeout=10
        )
        return bool(re.search(rb"(?:^|\s)ass\s", r.stdout, re.MULTILINE))
    except Exception:
        return False


def _has_drawtext() -> bool:
    try:
        r = subprocess.run(
            [_ffmpeg_path(), "-filters"], capture_output=True, timeout=10
        )
        return b"drawtext" in r.stdout
    except Exception:
        return False


def _init_ffmpeg_caps() -> tuple[bool, bool]:
    _l = _has_libass()
    _d = _has_drawtext()
    if _l:
        logger.info("Burn mode : Mode A libass")
    elif _d:
        logger.info("Burn mode : Mode B drawtext")
    else:
        logger.info("Burn mode : Mode C Pillow (rawvideo pipe)")
    return _l, _d


_LIBASS_OK: bool = False
_DRAWTEXT_OK: bool = False
_HWACCEL_ENCODER: str | None = None


def _detect_hwaccel() -> str:
    """Detecte le codec materiel dispo : videotoolbox > nvenc > vaapi > qsv > libx264.

    Le resultat est mis en cache pour les appels suivants.
    """
    global _HWACCEL_ENCODER
    if _HWACCEL_ENCODER is not None:
        return _HWACCEL_ENCODER
    ffmpeg = _ffmpeg_path()
    try:
        r = subprocess.run(
            [ffmpeg, "-encoders"], capture_output=True, timeout=10, text=True
        )
        for codec in ["h264_videotoolbox", "h264_vaapi", "h264_qsv"]:
            if codec in r.stdout:
                # Test rapide : essayer d'encoder 1 frame
                test_cmd = [ffmpeg, "-f", "lavfi", "-i", "color=c=black:s=64x64:d=0.04",
                           "-c:v", codec, "-f", "null", "-"]
                tr = subprocess.run(test_cmd, capture_output=True, timeout=5)
                if tr.returncode == 0:
                    _HWACCEL_ENCODER = codec
                    logger.info("HW accel detecte", extra={"encoder": codec})
                    return codec
    except Exception:
        pass
    _HWACCEL_ENCODER = "libx264"
    logger.info("HW accel non disponible, fallback libx264")
    return "libx264"


def init_ffmpeg_caps() -> tuple[bool, bool]:
    """Initialise les capacites FFmpeg (module-level)."""
    global _LIBASS_OK, _DRAWTEXT_OK
    _LIBASS_OK, _DRAWTEXT_OK = _init_ffmpeg_caps()
    return _LIBASS_OK, _DRAWTEXT_OK


def get_libass_ok() -> bool:
    return _LIBASS_OK


def get_drawtext_ok() -> bool:
    return _DRAWTEXT_OK


def _get_ffmpeg_encoding_options() -> list[str]:
    """
    Options video FFmpeg optimisees pour lecture fluide sur web (HTML5 <video>).

    Utilise l'acceleration materielle dispo via _detect_hwaccel().
    Les codecs GPU (videotoolbox, nvenc, vaapi, qsv) gerent
    le debit/qualite via -b:v, pas de -preset/-crf.
    """
    encoder = _detect_hwaccel()

    if encoder == "libx264":
        return [
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "20",
            "-g",
            "60",
            "-keyint_min",
            "30",
            "-sc_threshold",
            "0",
            "-bf",
            "2",
            "-profile:v",
            "high",
            "-level",
            "4.2",
            "-movflags",
            "+faststart",
            "-muxdelay",
            "0",
            "-pix_fmt",
            "yuv420p",
            "-threads",
            "0",
        ]

    # ── Hardware encoder ──────────────────────────────────────────────
    base_opts = [
        "-c:v",
        encoder,
    ]
    if encoder == "h264_videotoolbox":
        base_opts += ["-b:v", "2M"]
    else:
        base_opts += ["-b:v", "3M"]
    base_opts += [
        "-g",
        "60",
        "-keyint_min",
        "30",
        "-bf",
        "2",
        "-movflags",
        "+faststart",
        "-muxdelay",
        "0",
        "-pix_fmt",
        "yuv420p",
        "-threads",
        "0",
    ]

    # Tuning par encodeur
    if encoder == "h264_nvenc":
        base_opts.extend(["-profile:v", "high", "-rc", "vbr"])
    elif encoder == "h264_vaapi":
        base_opts.extend(["-profile:v", "high", "-rc_mode", "VBR"])

    return base_opts


def _get_video_dims(video: "Path") -> tuple[int, int]:

    ffprobe = _ffmpeg_path().replace("ffmpeg", "ffprobe")
    try:
        r = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height",
                "-of",
                "csv=p=0",
                str(video),
            ],
            capture_output=True,
            timeout=15,
        )
        if r.returncode == 0 and r.stdout:
            parts = r.stdout.decode().strip().split(",")
            return int(parts[0]), int(parts[1])
    except Exception:
        pass
    return 1280, 720


def _get_video_duration(video: "Path") -> float:

    ffprobe = _ffmpeg_path().replace("ffmpeg", "ffprobe")
    try:
        r = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(video),
            ],
            capture_output=True,
            timeout=15,
        )
        if r.returncode == 0 and r.stdout.strip():
            return float(r.stdout.decode().strip())
    except Exception:
        pass
    return 60.0


def _get_video_frames(video: "Path") -> int:
    """Returns the total number of frames in a video file."""

    ffprobe = _ffmpeg_path().replace("ffmpeg", "ffprobe")
    try:
        r = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=nb_frames",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(video),
            ],
            capture_output=True,
            timeout=15,
        )
        if r.returncode == 0 and r.stdout.strip():
            val = r.stdout.decode().strip()
            if val and val != "N/A":
                return int(val)
    except Exception:
        pass
    return 0


def _get_video_fps(video: "Path") -> float:

    ffprobe = _ffmpeg_path().replace("ffmpeg", "ffprobe")
    try:
        r = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=r_frame_rate",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(video),
            ],
            capture_output=True,
            timeout=15,
        )
        if r.returncode == 0 and r.stdout:
            frac = r.stdout.decode().strip()
            if "/" in frac:
                num, den = frac.split("/")
                return float(num) / float(den)
            return float(frac)
    except Exception:
        pass
    return 25.0
