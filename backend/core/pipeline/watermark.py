"""
pipeline/watermark.py — Generation watermark PNG — Subvox

Genere un PNG transparent avec un badge design en haut a droite (mode `fixed_logo`)
ou un motif tuile diagonal (mode `tiling`, legacy).

Le texte est lu depuis settings.WATERMARK_TEXT (par defaut
"Subtitled by Subvox").
Si settings.WATERMARK_LOGO_PATH pointe vers un fichier PNG existant,
le logo est utilisé a la place du badge texte.
"""

from __future__ import annotations

from pathlib import Path
from core.logging_setup import get_logger

logger = get_logger(__name__)


def _generate_watermark_png(
    vid_w: int,
    vid_h: int,
    text: str = "",
    mode: str = "fixed_logo",
    position: str = "top-right",
    bg_opacity: float = 0.55,
) -> bytes | None:
    """Genere un PNG transparent avec watermark.

    Modes:
        - ``fixed_logo``: badge design en coin (default)
        - ``tiling``: motif tuile diagonal repete (legacy)
    """
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        logger.error("Pillow non installe, watermark impossible")
        return None

    import os
    import math as _math
    from core.config import settings

    if not text:
        text = settings.WATERMARK_TEXT

    # ── Police ────────────────────────────────────────────────────────────────
    font_candidates = [
        "/System/Library/Fonts/Supplemental/Arial Unicode MS.ttf",
        "/System/Library/Fonts/HelveticaNeue.ttc",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    font_file = next((p for p in font_candidates if os.path.isfile(p)), None)

    if mode == "tiling":
        return _generate_tiling_watermark(vid_w, vid_h, text, font_file)
    return _generate_fixed_logo_watermark(
        vid_w, vid_h, text, font_file, position, bg_opacity
    )


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


def _get_logo_path() -> Path | None:
    """
    Retourne le chemin absolu du logo watermark.
    Cherche d'abord dans backend/assets/, puis a la racine du projet.
    """
    import os
    from pathlib import Path as _Path

    from core.config import settings

    logo_rel = settings.WATERMARK_LOGO_PATH
    if not logo_rel:
        return None

    # Chemin relatif depuis backend/
    backend_dir = _Path(__file__).parent.parent
    candidate = backend_dir / logo_rel
    if candidate.exists():
        return candidate

    # Fallback: racine du projet
    root_candidate = backend_dir.parent / logo_rel
    if root_candidate.exists():
        return root_candidate

    return None


def _generate_fixed_logo_watermark(
    vid_w: int,
    vid_h: int,
    text: str,
    font_file: str | None,
    position: str = "top-right",
    bg_opacity: float = 0.55,
) -> bytes | None:
    """
    Badge design pro avec zones de securite mathematiques.

    Si un logo PNG est configure (WATERMARK_LOGO_PATH), l'utilise
    a la place du badge texte.

    Rendu (texte):
        ┌────────────────────┐
        │           ▎Translated│  zone watermark (top 20%)
        │           ▎by       │
        │           ▎Subvox│
        ├────────────────────┤
        │     zone neutre     │  (20%-75%)
        ├────────────────────┤
        │   zone sous-titres   │  (75%-100%)
        │  sous-titres ici    │
        └────────────────────┘
    """
    try:
        from PIL import Image, ImageDraw, ImageFont, ImageFilter
    except ImportError:
        return None

    from io import BytesIO

    img = Image.new("RGBA", (vid_w, vid_h), (0, 0, 0, 0))

    # ── Bornes de sécurité ────────────────────────────────────────────────────
    min_x, min_y, max_x, max_y = _get_watermark_bounds(vid_w, vid_h, position)
    badge_max_w = max_x - min_x
    badge_max_h = max_y - min_y

    # ── Tenter d'utiliser le logo PNG ─────────────────────────────────────────
    logo_path = _get_logo_path()
    if logo_path:
        try:
            logo_img = Image.open(logo_path).convert("RGBA")
            # Redimensionner proportionnellement dans la safe zone
            logo_w, logo_h = logo_img.size
            scale = min(badge_max_w / logo_w, badge_max_h / logo_h)
            new_w = int(logo_w * scale)
            new_h = int(logo_h * scale)
            logo_resized = logo_img.resize((new_w, new_h), Image.LANCZOS)

            # Positionner selon la position configurée
            margin = max(16, int(vid_h * 0.02))
            margin_lr = max(16, int(vid_w * 0.02))

            if position == "top-right":
                lx = vid_w - new_w - margin_lr
                ly = margin
            elif position == "top-left":
                lx = margin_lr
                ly = margin
            else:
                lx = vid_w - new_w - margin_lr
                ly = margin

            img.paste(logo_resized, (lx, ly), logo_resized)

            buf = BytesIO()
            img.save(buf, format="PNG")
            logger.info(
                "Watermark logo PNG genere",
                extra={
                    "dims": f"{vid_w}x{vid_h}",
                    "logo": str(logo_path),
                    "position": position,
                    "logo_size": f"{new_w}x{new_h}",
                    "safe_zone": f"({min_x},{min_y})-({max_x},{max_y})",
                },
            )
            return buf.getvalue()
        except Exception as e:
            logger.warning(
                "Impossible de charger le logo PNG, fallback texte",
                extra={"error": str(e)},
            )

    # ── Fallback: badge texte ─────────────────────────────────────────────────
    draw = ImageDraw.Draw(img)

    # ── Taille de police (adaptative au badge) ────────────────────────────────
    base = min(vid_w, vid_h)
    fontsize_main = max(12, min(int(badge_max_h * 0.38), int(base * 0.035)))
    fontsize_sub = max(10, min(int(badge_max_h * 0.28), int(base * 0.025)))

    font_main = (
        ImageFont.truetype(font_file, fontsize_main)
        if font_file
        else ImageFont.load_default()
    )
    font_sub = (
        ImageFont.truetype(font_file, fontsize_sub)
        if font_file
        else ImageFont.load_default()
    )

    # ── Texte 2 lignes ───────────────────────────────────────────────────────
    line1 = "Subtitled by"
    line2 = "Subvox"

    bbox1 = draw.textbbox((0, 0), line1, font=font_main)
    bbox2 = draw.textbbox((0, 0), line2, font=font_sub)
    tw1 = bbox1[2] - bbox1[0]
    th1 = bbox1[3] - bbox1[1]
    tw2 = bbox2[2] - bbox2[0]
    th2 = bbox2[3] - bbox2[1]

    txt_w = max(tw1, tw2)
    txt_h = th1 + th2 + 6

    # ── Dimensions du badge (proportionnelles) ────────────────────────────────
    accent_w = max(3, int(badge_max_h * 0.06))
    padding_x = max(8, int(badge_max_h * 0.18))
    padding_y = max(6, int(badge_max_h * 0.14))
    badge_w = txt_w + padding_x * 2 + accent_w + 3
    badge_h = txt_h + padding_y * 2

    # Si le badge est trop large, reduire la police
    if badge_w > badge_max_w:
        scale = badge_max_w / badge_w
        fontsize_main = max(10, int(fontsize_main * scale))
        fontsize_sub = max(8, int(fontsize_sub * scale))
        font_main = (
            ImageFont.truetype(font_file, fontsize_main)
            if font_file
            else ImageFont.load_default()
        )
        font_sub = (
            ImageFont.truetype(font_file, fontsize_sub)
            if font_file
            else ImageFont.load_default()
        )
        bbox1 = draw.textbbox((0, 0), line1, font=font_main)
        bbox2 = draw.textbbox((0, 0), line2, font=font_sub)
        tw1, th1 = bbox1[2] - bbox1[0], bbox1[3] - bbox1[1]
        tw2, th2 = bbox2[2] - bbox2[0], bbox2[3] - bbox2[1]
        txt_w = max(tw1, tw2)
        txt_h = th1 + th2 + 6
        badge_w = txt_w + padding_x * 2 + accent_w + 3
        badge_h = txt_h + padding_y * 2

    # Si le badge est trop haut, reduire encore
    if badge_h > badge_max_h:
        scale = badge_max_h / badge_h
        fontsize_main = max(8, int(fontsize_main * scale))
        fontsize_sub = max(7, int(fontsize_sub * scale))
        font_main = (
            ImageFont.truetype(font_file, fontsize_main)
            if font_file
            else ImageFont.load_default()
        )
        font_sub = (
            ImageFont.truetype(font_file, fontsize_sub)
            if font_file
            else ImageFont.load_default()
        )
        bbox1 = draw.textbbox((0, 0), line1, font=font_main)
        bbox2 = draw.textbbox((0, 0), line2, font=font_sub)
        tw1, th1 = bbox1[2] - bbox1[0], bbox1[3] - bbox1[1]
        tw2, th2 = bbox2[2] - bbox2[0], bbox2[3] - bbox2[1]
        txt_w = max(tw1, tw2)
        txt_h = th1 + th2 + 6
        badge_w = txt_w + padding_x * 2 + accent_w + 3
        badge_h = txt_h + padding_y * 2

    radius = max(4, int(badge_h * 0.20))

    # ── Position centree dans la safe zone ────────────────────────────────────
    if position == "top-right":
        bx = max_x - badge_w
        by = min_y
    elif position == "top-left":
        bx = min_x
        by = min_y
    else:
        bx = max_x - badge_w
        by = min_y

    # ── Ombre portee ──────────────────────────────────────────────────────────
    shadow_img = Image.new("RGBA", (badge_w, badge_h), (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow_img)
    shadow_draw.rounded_rectangle(
        (0, 0, badge_w, badge_h),
        radius=radius,
        fill=(0, 0, 0, 90),
    )
    shadow_img = shadow_img.filter(ImageFilter.BoxBlur(4))
    img.paste(shadow_img, (bx + 3, by + 3), shadow_img)

    # ── Fond du badge (noir semi-transparent) ────────────────────────────────
    alpha = max(0, min(255, int(bg_opacity * 255)))
    badge_overlay = Image.new("RGBA", (badge_w, badge_h), (0, 0, 0, 0))
    badge_draw = ImageDraw.Draw(badge_overlay)
    badge_draw.rounded_rectangle(
        (0, 0, badge_w, badge_h),
        radius=radius,
        fill=(0, 0, 0, alpha),
    )
    img.paste(badge_overlay, (bx, by), badge_overlay)

    # ── Barre de couleur verticale (accent) ─────────────────────────────────
    accent_color = (59, 130, 246, 200)  # bleu vif #3B82F6
    accent_x = bx + max(4, int(badge_h * 0.06))
    accent_y1 = by + max(4, int(badge_h * 0.08))
    accent_y2 = by + badge_h - max(4, int(badge_h * 0.08))
    draw.rectangle(
        (accent_x, accent_y1, accent_x + accent_w, accent_y2),
        fill=accent_color,
    )

    # ── Liseré blanc semi-transparent ────────────────────────────────────────
    border_layer = Image.new("RGBA", (badge_w, badge_h), (0, 0, 0, 0))
    border_draw = ImageDraw.Draw(border_layer)
    border_draw.rounded_rectangle(
        (0, 0, badge_w - 1, badge_h - 1),
        radius=radius,
        outline=(255, 255, 255, 55),
        width=1,
    )
    img.paste(border_layer, (bx, by), border_layer)

    # ── Texte centré dans le badge ────────────────────────────────────────────
    offset_x = accent_w + 3
    content_center_x = bx + (badge_w + offset_x) // 2
    tx = content_center_x - tw1 // 2
    ty1 = by + padding_y
    draw.text((tx, ty1), line1, fill=(255, 255, 255, 220), font=font_main)

    tx2 = content_center_x - tw2 // 2
    ty2 = ty1 + th1 + 6
    draw.text((tx2, ty2), line2, fill=(255, 255, 255, 180), font=font_sub)

    buf = BytesIO()
    img.save(buf, format="PNG")
    logger.info(
        "Watermark fixed_logo generated",
        extra={
            "dims": f"{vid_w}x{vid_h}",
            "text": text,
            "position": position,
            "badge_size": f"{badge_w}x{badge_h}",
            "safe_zone": f"({min_x},{min_y})-({max_x},{max_y})",
            "font_main": fontsize_main,
            "font_sub": fontsize_sub,
        },
    )
    return buf.getvalue()


def _generate_tiling_watermark(
    vid_w: int, vid_h: int, text: str, font_file: str | None
) -> bytes | None:
    """Legacy : motif tuile diagonal repete."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return None

    from io import BytesIO

    fontsize = max(16, int(min(vid_w, vid_h) * 0.03))
    font = (
        ImageFont.truetype(font_file, fontsize)
        if font_file
        else ImageFont.load_default()
    )

    img = Image.new("RGBA", (vid_w, vid_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]

    step_x = max(tw + 80, 350)
    step_y = max(th + 60, 220)

    diag_img = Image.new("RGBA", (vid_w, vid_h), (0, 0, 0, 0))
    diag_draw = ImageDraw.Draw(diag_img)

    row = 0
    y = -step_y
    while y < vid_h + step_y:
        offset_x = (row % 2) * (step_x // 2)
        x = -step_x + offset_x
        while x < vid_w + step_x:
            diag_draw.text(
                (x, y),
                text,
                fill=(255, 255, 255, 70),
                font=font,
            )
            x += step_x
        y += step_y
        row += 1

    angle_deg = -30
    cx, cy = vid_w // 2, vid_h // 2
    diag_rotated = diag_img.rotate(angle_deg, center=(cx, cy), expand=False)
    img = Image.alpha_composite(img, diag_rotated)

    buf = BytesIO()
    img.save(buf, format="PNG")
    logger.info(
        "Watermark tiling generated",
        extra={
            "dims": f"{vid_w}x{vid_h}",
            "text": text,
            "step": f"{step_x}x{step_y}",
            "angle": angle_deg,
            "alpha": 70,
        },
    )
    return buf.getvalue()


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
