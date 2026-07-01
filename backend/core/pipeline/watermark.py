"""
pipeline/watermark.py — Generation watermark sporadique — Subvox

Genere des timecodes et filtres drawtext pour un overlay texte
sporadique customisable par l'utilisateur.

Le watermark n'est plus un PNG — c'est un overlay drawtext FFmpeg
genere lors de l'etape de burn.
"""

from __future__ import annotations

from core.logging_setup import get_logger

logger = get_logger(__name__)


def _generate_watermark_png(
    vid_w: int,
    vid_h: int,
    text: str = "",
    mode: str = "sporadic",
    position: str = "top-right",
    bg_opacity: float = 0.55,
) -> bytes | None:
    """Obsolete — le watermark n'est plus un PNG.

    Le watermark est genere via drawtext dans l'etape de burn.
    Cette fonction retourne toujours None.
    """
    return None


def _get_watermark_bounds(
    vid_w: int, vid_h: int, position: str
) -> tuple[int, int, int, int]:
    """
    Calcule les bornes du watermark en utilisant SubtitleConfig.
    Retourne (min_x, min_y, max_x, max_y) en pixels.
    Le watermark doit etre entierement dans la zone watermark (top 20%).
    """
    from core.subtitle_config import SubtitleConfig

    config = SubtitleConfig(vid_w, vid_h)
    _, zone_bottom = config.get_watermark_safe_zone()
    max_w, max_h = config.get_watermark_max_dims()

    zone_bottom_px = int(vid_h * zone_bottom)
    margin = max(16, int(vid_h * 0.02))
    margin_lr = max(16, int(vid_w * 0.02))

    if position == "top-right":
        return (
            vid_w - max_w - margin_lr,
            margin,
            vid_w - margin_lr,
            min(zone_bottom_px - margin, margin + max_h),
        )
    elif position == "top-left":
        return (
            margin_lr,
            margin,
            margin_lr + max_w,
            min(zone_bottom_px - margin, margin + max_h),
        )
    else:
        return (vid_w - max_w - margin_lr, margin, vid_w - margin_lr, margin + max_h)


def _compute_sporadic_timecodes(
    duration_s: float,
    interval: float = 10,
    text_duration: float = 4,
) -> list[tuple[float, float]]:
    """Genere une liste de (start, end) pour les apparitions sporadiques du texte.

    Le premier decalage est aleatoire (5-15s) pour eviter la syncro parfaite.
    """
    import random as _random

    timecodes: list[tuple[float, float]] = []
    cursor = _random.uniform(5, 15)  # premier decalage aleatoire
    while cursor < duration_s:
        end = min(cursor + text_duration, duration_s)
        timecodes.append((cursor, end))
        # Intervalle aleatoire entre 15 et 20s
        cursor += _random.uniform(interval, interval + 5)
    return timecodes


def _build_sporadic_drawtext_filters(
    vid_w: int,
    vid_h: int,
    text: str,
    timecodes: list[tuple[float, float]],
    opacity: float = 0.6,
    fontsize: int | None = None,
) -> tuple[str, str]:
    """Construit la chaine de filtres drawtext pour les apparitions sporadiques.

    Retourne (filter_chain, last_label).
    Chaque occurrence apparait a une position differente (rotation 4 positions)
    avec un fond semi-transparent et sans depasser la zone sous-titres.

    Positions cycliques (evitent la zone sous-titres en bas):
        - ``top-right``: x=W-tw-40, y=H*0.08
        - ``top-left``:  x=40,      y=H*0.08
        - ``bottom-right``: x=W-tw-40, y=H*0.55
        - ``bottom-left``:  x=40,      y=H*0.55
    """
    if not timecodes or not text.strip():
        return "", "base"

    if fontsize is None:
        fontsize = max(18, min(32, int(min(vid_w, vid_h) * 0.028)))

    # Positions au centre (evitent la zone sous-titres en bas)
    positions = [
        ("x=(W-text_w)/2", "y=H*0.05"),   # haut centre
        ("x=(W-text_w)/2", "y=H*0.35"),   # milieu haut
        ("x=(W-text_w)/2", "y=H*0.55"),   # milieu bas
        ("x=(W-text_w)/2", "y=H*0.80"),   # bas (mais pas sur les sous-titres)
    ]

    fontcolor = f"white@{opacity}"
    # Fond semi-transparent derriere le texte
    boxcolor = "black@0.25"

    # Echapper les caracteres speciaux FFmpeg dans le texte
    escaped = text.replace(":", "\\:").replace("'", "\\\\'")

    filters: list[str] = []
    current_label = "base"

    for i, (start, end) in enumerate(timecodes):
        next_label = f"s{i}"
        pos_x, pos_y = positions[i % len(positions)]
        enable_str = f"between(t,{start:.1f},{end:.1f})"
        filter_str = (
            f"[{current_label}]drawtext="
            f"text='{escaped}'"
            f":fontsize={fontsize}"
            f":fontcolor={fontcolor}"
            f":box=1:boxcolor={boxcolor}:boxborderw=8"
            f":{pos_x}:{pos_y}"
            f":enable='{enable_str}'"
            f"[{next_label}]"
        )
        filters.append(filter_str)
        current_label = next_label

    return ";\n".join(filters), current_label
