"""
pipeline/srt.py — Helpers SRT/ASS (parsing, timing, conversion) — Subvox
"""

import textwrap
import re
from pathlib import Path

from core.logging_setup import get_logger
from core.pipeline.ffmpeg import _get_video_dims

logger = get_logger(__name__)


# ─── Time helpers ──────────────────────────────────────────────────────────────


def _to_srt_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds - int(seconds)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _parse_time_to_seconds(ts: str) -> float:
    """Convertit un timestamp SRT (00:00:01,000) en secondes."""
    ts = ts.strip().replace(",", ".")
    h, m, s_ms = ts.split(":")
    s, ms = s_ms.split(".")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0


def _srt_time_to_ass(ts: str) -> str:
    """Convertit un timestamp SRT (00:00:01,000) en format ASS (0:00:01.00)."""
    ts = ts.strip().replace(",", ".")
    parts = ts.split(":")
    h = int(parts[0])
    m = int(parts[1])
    rest = parts[2].split(".")
    s = int(rest[0])
    ms = int(rest[1]) if len(rest) > 1 else 0
    cs = ms // 10
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


# ─── SRT parsing / writing ─────────────────────────────────────────────────────


def _parse_srt(content: str) -> list[dict]:
    blocks = []
    for raw_block in content.strip().split("\n\n"):
        lines = raw_block.strip().splitlines()
        if len(lines) < 3:
            continue
        blocks.append(
            {
                "index": lines[0].strip(),
                "timecode": lines[1].strip(),
                "text": "\n".join(lines[2:]).strip(),
            }
        )
    return blocks


def _write_srt(blocks: list[dict]) -> str:
    parts = []
    for b in blocks:
        parts.append(f"{b['index']}\n{b['timecode']}\n{b['text']}\n")
    return "\n".join(parts)


def _shift_srt_timing(srt_content: str, offset_ms: int) -> str:
    """
    Decale tous les timestamps d'un SRT de `offset_ms` millisecondes.
    """
    if not srt_content.strip() or offset_ms == 0:
        return srt_content

    offset_s = offset_ms / 1000.0
    blocks = _parse_srt(srt_content)

    shifted_blocks = []
    for block in blocks:
        try:
            start_str, end_str = block["timecode"].split(" --> ")
            start_s = _parse_time_to_seconds(start_str)
            end_s = _parse_time_to_seconds(end_str)
            start_s += offset_s
            end_s += offset_s
            start_s = max(0.0, start_s)
            end_s = max(0.0, end_s)
            block = block.copy()
            block["timecode"] = f"{_to_srt_time(start_s)} --> {_to_srt_time(end_s)}"
            shifted_blocks.append(block)
        except Exception:
            shifted_blocks.append(block)

    return _write_srt(shifted_blocks)


def _adjust_duration_based_on_text(
    start_seconds: float,
    end_seconds: float,
    text_length: int,
    min_chars_per_second: float = 17.0,
    min_duration: float = 1.2,
) -> tuple[float, float]:
    """
    Ajuste la duree d'affichage en fonction de la longueur du texte.
    """
    required_duration = max(min_duration, text_length / min_chars_per_second)
    current_duration = end_seconds - start_seconds
    if current_duration < required_duration:
        end_seconds = start_seconds + required_duration + 0.2
    return start_seconds, end_seconds


# ─── SRT → ASS ─────────────────────────────────────────────────────────────────


def _srt_to_ass(
    srt_content: str,
    vid_w: int = 1280,
    vid_h: int = 720,
    user_style: dict | None = None,
) -> str:
    """
    Version amelioree utilisant subtitle_config.py pour une adaptation automatique.
    """
    from core.subtitle_config import SubtitleConfig, load_user_style_from_json

    style_dict = None
    if isinstance(user_style, str):
        style_dict = load_user_style_from_json(user_style)
    elif isinstance(user_style, dict):
        style_dict = user_style

    config = SubtitleConfig(vid_w, vid_h, style_dict)

    if not style_dict or "background_opacity" not in style_dict:
        config.defaults["default_opacity"] = 100

    font_size = config.calculate_font_size()
    max_chars_per_line = config.calculate_max_chars_per_line()
    margin_lr, margin_r, margin_v = config.calculate_margins()

    orientation = "VERTICAL" if config.is_vertical else "HORIZONTAL"
    logger.info(
        f"ASS config: {vid_w}x{vid_h} -> {orientation}",
        extra={
            "font_size": font_size,
            "max_chars_per_line": max_chars_per_line,
            "margin_lr": margin_lr,
            "margin_v": margin_v,
        },
    )

    # ====================== HEADER ASS ======================
    header = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        f"PlayResX: {vid_w}\n"
        f"PlayResY: {vid_h}\n"
        "WrapStyle: 0\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"{config.to_ass_style()}\n"
        "\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )

    # ====================== SMART WRAP ======================
    def smart_wrap(text: str, max_chars: int) -> str:
        """
        Découpe intelligemment un texte en lignes de max_chars caractères max.
        Le splitter en amont (split_srt_advanced) garantit déjà que les segments
        tiennent dans max_chars x 2 lignes. Cette fonction ne fait que reformater
        proprement sans jamais tronquer.
        """
        text = text.replace("\n", " ").strip()
        if len(text) <= max_chars * 1.7:
            return textwrap.fill(text, max_chars)

        sentences = re.split(r"([.!?])\s+", text)
        lines = []
        current = ""
        for i in range(0, len(sentences), 2):
            part = (
                sentences[i] + (sentences[i + 1] if i + 1 < len(sentences) else "")
            ).strip()
            if current and len(current + " " + part) > max_chars:
                lines.append(current)
                current = part
            else:
                current = (current + " " + part).strip()
        if current:
            lines.append(current)

        # Filet de sécurité : si > 2 lignes, forcer un nouveau wrapping
        # sans perte de contenu (au lieu de tronquer avec "...")
        if len(lines) > 2:
            # Fusionner les lignes excédentaires dans les 2 premières
            overflow = "\n".join(lines[2:])
            # Si la 2e ligne peut absorber le surplus, l'ajouter
            remaining = max_chars - len(lines[1]) - 1
            if remaining > 10 and len(overflow) <= remaining:
                lines[1] = lines[1] + " " + overflow
            else:
                lines[1] = lines[1] + " " + overflow[:max_chars]

        return "\n".join(lines[:2])

    # ====================== CONVERSION ======================
    blocks = _parse_srt(srt_content)
    event_lines = []

    for b in blocks:
        try:
            parts = b["timecode"].split(" --> ")
            t_start = _srt_time_to_ass(parts[0])
            t_end = _srt_time_to_ass(parts[1])

            raw = b["text"].replace("\n", " ").strip()
            wrapped = smart_wrap(raw, max_chars_per_line)
            ass_text = wrapped.replace("\n", "\\N")

            # ASS colors: &HAABBGGRR (AA=alpha, BB=blue, GG=green, RR=red)
            # BorderStyle=3 dans le style => box opaque remplie par \3c (OutlineColour)
            # Tous les tags DOIVENT utiliser 8 digits (AA+RRGGBB) pour garantir alpha=FF
            #   \3c&HFF000000& = outline noir opaque -> remplit la box
            #   \4c&HFF000000& = back noir opaque -> ombre de la box
            #   \c&HFFFFFF&    = texte blanc
            #   bord4          = bordure epaisse pour padding interne visible
            #   shad0          = pas d'ombre separee (le fond suffit)
            bg_color = (
                "00000000"  # noir opaque (AA=00=opaque en ASS, BB=00, GG=00, RR=00)
            )
            text_color = "FFFFFF"  # blanc
            ass_text = (
                f"{{\\bord4\\shad0"
                f"\\c&H{text_color}&"
                f"\\3c&H{bg_color}&"
                f"\\4c&H{bg_color}&"
                f"}}{ass_text}"
            )
            logger.debug(
                "ASS inline tags: "
                f"c=white, 3c=black(alpha=FF), 4c=black(alpha=FF), "
                f"bord=4, shad=0"
            )

            event_lines.append(
                f"Dialogue: 0,{t_start},{t_end},Default,,0,0,0,,{ass_text}"
            )
        except Exception:
            continue

    return header + "\n".join(event_lines) + "\n"
