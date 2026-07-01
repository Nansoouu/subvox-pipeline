"""
core/whisper_hallucination_filter.py — Filtre les hallucinations de Whisper — Subvox
Filtre les répétitions, bruits parasites, et patterns de "thank you".
"""

from __future__ import annotations

import re
from typing import Optional

from core.logging_setup import get_logger

logger = get_logger(__name__)

# Patterns d'hallucinations connus
HALLUCINATION_PATTERNS: list[re.Pattern] = [
    re.compile(
        r"^(thank you|thanks for watching|subscribe|like this video)", re.IGNORECASE
    ),
    re.compile(r"^[:\s]*♫|♪|♬"),
    re.compile(r"^[Mm]usic"),
    re.compile(r"^\[.*music.*\]", re.IGNORECASE),
    re.compile(r"^(applause|laughter|cheering|clapping)", re.IGNORECASE),
]

# Seuils de répétition
MAX_CONSECUTIVE_REPEAT = 3
MAX_SIMILARITY_RATIO = 0.85


def _is_cjk(text: str) -> bool:
    """Détecte si le texte contient majoritairement des caractères CJK (japonais, chinois, coréen)."""
    if not text.strip():
        return False
    cjk_count = sum(
        1
        for c in text
        if (
            "\u4e00" <= c <= "\u9fff"  # CJK Unified Ideographs
            or "\u3040" <= c <= "\u309f"  # Hiragana
            or "\u30a0" <= c <= "\u30ff"  # Katakana
            or "\uac00" <= c <= "\ud7af"  # Hangul
        )
    )
    return cjk_count / max(len(text), 1) > 0.3


def is_hallucination(text: str) -> bool:
    """Détecte si un texte est probablement une hallucination."""
    if not text or not text.strip():
        return True

    cleaned = text.strip()
    if len(cleaned) < 3:
        return True

    for pattern in HALLUCINATION_PATTERNS:
        if pattern.match(cleaned):
            return True

    return False


def filter_segment_hallucinations(segments: list[dict]) -> list[dict]:
    """
    Filtre les segments hallucinés d'une transcription Whisper.
    Garde les segments valides seulement.
    """
    filtered = []
    removed = 0

    for seg in segments:
        text = seg.get("text", "").strip()
        if not text:
            removed += 1
            continue

        if is_hallucination(text):
            removed += 1
            continue

        # Suppression des segments trop courts
        if len(text.split()) <= 1:
            removed += 1
            continue

        filtered.append(seg)

    if removed:
        logger.info(
            f"Filtre hallucinations : {removed} segments supprimés sur {len(segments)}"
        )

    return filtered


def detect_repeated_words(words: list[str]) -> Optional[str]:
    """Détecte les répétitions de mots dans une séquence."""
    if len(words) < MAX_CONSECUTIVE_REPEAT * 2:
        return None

    for i in range(len(words) - MAX_CONSECUTIVE_REPEAT + 1):
        candidate = words[i]
        if all(
            w.lower() == candidate.lower()
            for w in words[i : i + MAX_CONSECUTIVE_REPEAT]
        ):
            return candidate

    return None


def filter_hallucinations_regex(blocks: list[dict]) -> tuple[list[dict], int]:
    """
    Filtre les blocs SRT hallucinés via patterns regex.

    Retourne (blocs_filtrés, nombre_supprimés).
    Compatible avec l'interface attendue par runner.py.
    """
    filtered = []
    removed = 0

    for block in blocks:
        text = block.get("text", "").strip()
        if not text or is_hallucination(text):
            removed += 1
            continue
        # Skip le check "len(split) <= 1" pour les langues CJK (japonais, chinois, coréen)
        # car elles n'ont pas d'espaces entre les mots
        if not _is_cjk(text) and len(text.split()) <= 1:
            removed += 1
            continue
        filtered.append(block)

    return filtered, removed


async def apply_llm_hallucination_filter(
    blocks: list[dict],
    transcript_tx: str,
) -> tuple[int, int]:
    """
    Filtre les hallucinations via LLM (placeholder).

    Actuellement, ne fait que reporter le nombre de blocs.
    Retourne (nb_hallucinations_supprimées, nb_no_audio).
    Compatible avec l'interface attendue par runner.py.
    """
    _ = transcript_tx  # reserve pour future implémentation LLM
    return 0, 0
