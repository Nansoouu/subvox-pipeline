"""
pipeline/duration_tiers.py — Paliers de durée vidéo — Subvox

Définit 5 paliers de durée (T1-T5) qui adaptent automatiquement :
- Le chunking traduction (max_chars, max_blocks)
- La durée minimale des segments sous-titres
- Le nombre de paragraphes du résumé
- La sélection des meilleurs segments (ratio)
- Le type de prompt SEO

Utilisation :
    from core.pipeline.duration_tiers import get_tier

    tier = get_tier(duration_s=120.0)
    print(tier.seo_prompt_type)  # "short"
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


SeoPromptType = Literal["short", "standard", "longform"]


@dataclass(frozen=True)
class DurationTier:
    """
    Profil de configuration pour un palier de durée vidéo.

    Tous les champs sont en secondes ou en valeurs absolues,
    sauf segment_selection_ratio (0.0-1.0).
    """

    name: str  # Identifiant court : "short", "court", "moyen", "long", "tres_long"
    label: str  # Libellé lisible : "Short/Reel", "Court", "Moyen", "Long", "Très long"

    # Seuils (inclusif pour min, exclusif pour max sauf dernier palier)
    min_duration_s: float
    max_duration_s: float

    # ── Chunking traduction (srt_chunking.py) ──────────────────────────
    max_chars_per_chunk: int  # Nombre max de caractères par chunk
    max_blocks_per_chunk: int  # Nombre max de blocs SRT par chunk

    # ── Segments sous-titres (subtitle_splitter.py) ────────────────────
    min_segment_duration_s: float  # Durée minimale d'un segment SRT
    subsegment_min_duration_s: float  # Durée minimale d'un sous-segment

    # ── Résumé (openrouter.py:generate_adaptive_summary) ───────────────
    summary_max_paragraphs: int  # Nombre max de paragraphes
    summary_max_chars_per_para: int  # Caractères max par paragraphe

    # ── Sélection des meilleurs segments (pour preview/clips) ──────────
    segment_selection_ratio: float  # Ratio de segments à conserver (1.0 = tous)

    # ── SEO (seo.py) ────────────────────────────────────────────────────
    seo_prompt_type: SeoPromptType  # Type de prompt SEO à utiliser


# ─── Définition des 5 paliers ────────────────────────────────────────────────

TIERS: dict[str, DurationTier] = {
    "T1_short": DurationTier(
        name="T1_short",
        label="Short/Reel",
        min_duration_s=0.0,
        max_duration_s=120.0,  # ≤ 2 min
        max_chars_per_chunk=8000,
        max_blocks_per_chunk=60,
        min_segment_duration_s=0.4,
        subsegment_min_duration_s=0.6,
        summary_max_paragraphs=1,
        summary_max_chars_per_para=200,
        segment_selection_ratio=1.0,
        seo_prompt_type="short",
    ),
    "T2_court": DurationTier(
        name="T2_court",
        label="Court",
        min_duration_s=120.0,
        max_duration_s=300.0,  # 2-5 min
        max_chars_per_chunk=6000,
        max_blocks_per_chunk=50,
        min_segment_duration_s=0.6,
        subsegment_min_duration_s=0.8,
        summary_max_paragraphs=1,
        summary_max_chars_per_para=250,
        segment_selection_ratio=1.0,
        seo_prompt_type="standard",
    ),
    "T3_moyen": DurationTier(
        name="T3_moyen",
        label="Moyen",
        min_duration_s=300.0,
        max_duration_s=900.0,  # 5-15 min
        max_chars_per_chunk=4000,
        max_blocks_per_chunk=40,
        min_segment_duration_s=0.8,
        subsegment_min_duration_s=1.0,
        summary_max_paragraphs=2,
        summary_max_chars_per_para=300,
        segment_selection_ratio=1.0,
        seo_prompt_type="standard",
    ),
    "T4_long": DurationTier(
        name="T4_long",
        label="Long",
        min_duration_s=900.0,
        max_duration_s=1800.0,  # 15-30 min
        max_chars_per_chunk=3000,
        max_blocks_per_chunk=30,
        min_segment_duration_s=1.0,
        subsegment_min_duration_s=1.2,
        summary_max_paragraphs=3,
        summary_max_chars_per_para=350,
        segment_selection_ratio=0.5,
        seo_prompt_type="longform",
    ),
    "T5_tres_long": DurationTier(
        name="T5_tres_long",
        label="Très long",
        min_duration_s=1800.0,
        max_duration_s=float("inf"),  # > 30 min
        max_chars_per_chunk=2000,
        max_blocks_per_chunk=25,
        min_segment_duration_s=1.2,
        subsegment_min_duration_s=1.5,
        summary_max_paragraphs=5,
        summary_max_chars_per_para=400,
        segment_selection_ratio=0.3,
        seo_prompt_type="longform",
    ),
}


def get_tier(duration_s: float) -> DurationTier:
    """
    Retourne le palier de durée correspondant à la durée vidéo (en secondes).

    Args:
        duration_s: Durée de la vidéo en secondes.

    Returns:
        Une instance DurationTier correspondant au palier.
    """
    if duration_s <= 120.0:
        return TIERS["T1_short"]
    elif duration_s <= 300.0:
        return TIERS["T2_court"]
    elif duration_s <= 900.0:
        return TIERS["T3_moyen"]
    elif duration_s <= 1800.0:
        return TIERS["T4_long"]
    else:
        return TIERS["T5_tres_long"]


def tier_from_category(video_category: str | None = None) -> str | None:
    """
    Convertit une catégorie vidéo (issue de compute_video_category ou video_type)
    en un nom de tier. Utile pour les jobs legacy qui n'ont pas duration_tier stocké.

    Mapping :
        "short"  → "T1_short"
        "medium" → "T3_moyen"
        "long"   → "T5_tres_long"
    """
    mapping = {
        "short": "T1_short",
        "medium": "T3_moyen",
        "long": "T5_tres_long",
    }
    return mapping.get(video_category) if video_category else None