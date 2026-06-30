"""
subtitle_splitter.py — Découpage intelligent des segments SRT par caractères/lignes
Version 2 : basée sur max_chars_per_line + max_lines + résolution adaptative.

Stratégie :
- max_chars_per_line=42 pour Full HD (adaptatif 720p→4K)
- max_lines=2 (jamais plus de 2 lignes à l'écran)
- Timing proportionnel au nombre de caractères + bonus fin de phrase
- Préservation des styles HTML (<i>, <b>) et des tirets de dialogue
- Pas d'orphelins (mot seul sur un segment interdit)
- Fusion post-découpage des segments trop courts
"""

from __future__ import annotations

import re
from typing import Dict, List, Tuple

# ─── Paramètres par défaut ──────────────────────────────────────────────────

DEFAULT_MAX_CHARS_PER_LINE = 42
DEFAULT_MAX_LINES = 2
DEFAULT_MIN_DURATION_S = 0.7
DEFAULT_MIN_SEGMENT_DURATION_S = 0.5
DEFAULT_MAX_GAP_S = 0.03
DEFAULT_OVERLAP_S = 0.04


# ─── Helpers ────────────────────────────────────────────────────────────────


def _count_words(text: str) -> int:
    """Compte le nombre de mots dans un texte."""
    return len(text.split())


def _parse_time_to_seconds(ts: str) -> float:
    """Convertit un timestamp SRT (00:00:01,000) en secondes."""
    ts = ts.strip().replace(",", ".")
    parts = ts.split(":")
    h = int(parts[0])
    m = int(parts[1])
    s_ms = parts[2].split(".")
    s = int(s_ms[0])
    ms = int(s_ms[1]) if len(s_ms) > 1 else 0
    return h * 3600 + m * 60 + s + ms / 1000.0


def _to_srt_time(seconds: float) -> str:
    """Convertit des secondes en timestamp SRT (00:00:01,000)."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds - int(seconds)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _parse_srt_timecode(timecode: str) -> Tuple[float, float]:
    """Parse un timecode SRT (00:00:01,000 --> 00:00:05,000) en (start, end) secondes."""
    try:
        start_str, end_str = timecode.split(" --> ")
        return _parse_time_to_seconds(start_str), _parse_time_to_seconds(end_str)
    except (ValueError, IndexError):
        return 0.0, 0.0


def _parse_srt(srt_content: str) -> List[Dict[str, str]]:
    """Parse un SRT en blocs."""
    blocks = []
    for raw_block in srt_content.strip().split("\n\n"):
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


def _write_srt(blocks: List[Dict]) -> str:
    """Réécrit les blocs en format SRT avec index séquentiels."""
    parts = []
    for i, block in enumerate(blocks, 1):
        parts.append(f"{i}\n{block['timecode']}\n{block['text']}\n")
    return "\n".join(parts)


def _strip_styles(text: str) -> str:
    """Supprime les balises de style HTML/ASS pour le calcul de longueur."""
    # Supprime <i>, </i>, <b>, </b>
    text = re.sub(r"</?[ib]>", "", text)
    return text


# ─── Résolution adaptative ──────────────────────────────────────────────────


def get_max_chars_for_resolution(width: int = 1920, height: int = 1080) -> int:
    """Calcule le nombre max de caractères par ligne selon la résolution."""
    if width >= 3840:  # 4K
        return 48
    elif width >= 2560:  # 1440p / 2K
        return 45
    elif width >= 1920:  # Full HD
        return 42
    else:  # 720p et en dessous
        return 35


# ─── Découpage texte optimal ────────────────────────────────────────────────


def _split_text_optimal(
    text: str,
    max_chars: int = 42,
    max_lines: int = 2,
) -> List[str]:
    """
    Découpe le texte en segments qui maximisent l'espace écran.
    Chaque segment peut contenir 1 ou 2 lignes (séparées par \\n).

    Règles :
    - Chaque ligne ne dépasse pas max_chars caractères
    - Pas de mot coupé (on coupe aux espaces)
    - Pas d'orphelin (mot seul sur une ligne)
    - Priorité aux coupures sur . ! ? … puis , ; : puis espaces
    - Respect des tirets de dialogue (on garde ensemble si possible)

    Retourne une liste de segments (chaque segment = 1 ou 2 lignes).
    """
    # Nettoyage
    text = re.sub(r"\s+", " ", text.strip())
    if not text:
        return []

    # On travaille sans les styles pour les calculs de longueur
    # mais on garde les styles dans le texte original
    raw_text = text

    if len(raw_text) <= max_chars:
        return [text]

    words = raw_text.split()
    segments: List[str] = []

    # Construction segment par segment
    pos = 0
    while pos < len(words):
        # Combien de lignes dans ce segment ? Toujours 1 ou 2
        # On essaie de remplir 2 lignes si possible
        segment_words: List[str] = []

        for line_idx in range(max_lines):
            line_words: List[str] = []

            while pos < len(words):
                word = words[pos]
                test_line = " ".join(line_words + [word]) if line_words else word

                if len(test_line) <= max_chars:
                    line_words.append(word)
                    pos += 1
                else:
                    break

            # Si on n'a rien mis sur cette ligne, c'est qu'on a fini
            if not line_words:
                break

            segment_words.append(" ".join(line_words))

            # Vérifier l'orphelin : si la ligne suivante (si elle existe
            # et qu'on peut l'ajouter) ferait < 3 mots ou < 8 chars,
            # on l'incorpore dans la ligne courante
            if pos < len(words) and len(segment_words) < max_lines:
                next_word = words[pos]
                # Est-ce que le mot suivant tient dans la ligne courante ?
                test_merge = segment_words[-1] + " " + next_word
                if len(test_merge) <= max_chars:
                    segment_words[-1] = test_merge
                    pos += 1

        if segment_words:
            segments.append("\n".join(segment_words))

    # Post-traitement : éliminer les orphelins dans chaque segment
    cleaned: List[str] = []
    for seg in segments:
        lines = seg.split("\n")
        fixed: List[str] = []
        for line in lines:
            words_in_line = line.split()
            # Si une ligne n'a qu'un seul mot et que ce n'est pas la seule ligne,
            # on la fusionne avec la ligne précédente
            if len(words_in_line) == 1 and len(fixed) > 0:
                test_merge = fixed[-1] + " " + line
                if len(test_merge) <= max_chars * 1.5:
                    fixed[-1] = test_merge
                else:
                    fixed.append(line)
            else:
                fixed.append(line)
        cleaned.append("\n".join(fixed))

    # Dernier garde-fou : si après tout ça on a des segments vides ou orphelins
    result = [seg for seg in cleaned if seg and len(seg.strip()) > 0]
    return result if result else [text]


def _calculate_duration_weights(text_segments: List[str]) -> List[float]:
    """Poids basé sur le nombre de caractères + bonus pour les fins de phrases."""
    if not text_segments:
        return []

    weights = []
    for seg in text_segments:
        weight = float(len(seg))
        # Bonus si fin de phrase (on veut un peu plus de temps)
        if re.search(r"[.!?…]$", seg.strip()):
            weight *= 1.15
        weights.append(weight)

    total = sum(weights)
    if total <= 0:
        return [1.0 / len(text_segments)] * len(text_segments)
    return [w / total for w in weights]


# ─── Découpage d'un bloc ────────────────────────────────────────────────────


def _split_single_block_v2(
    block: Dict[str, str],
    max_chars_per_line: int = 42,
    max_lines: int = 2,
    min_duration_s: float = 0.7,
    overlap_s: float = 0.04,
) -> List[Dict[str, str]]:
    """
    Découpe un bloc SRT en sous-blocs basés sur le nombre de caractères/lignes.

    Args:
        block: Bloc SRT original {index, timecode, text}
        max_chars_per_line: Nombre max de caractères par ligne
        max_lines: Nombre max de lignes par sous-bloc
        min_duration_s: Durée minimale en secondes pour un sous-bloc
        overlap_s: Chevauchement en secondes entre sous-blocs

    Returns:
        Liste de sous-blocs, ou [block] si pas de découpage nécessaire
    """
    text = block["text"].strip()
    if not text:
        return [block]

    # Nettoyer les styles pour le calcul de longueur
    clean_text = _strip_styles(text)

    # Pas besoin de découper si le texte tient dans les limites
    if len(clean_text) <= max_chars_per_line * max_lines:
        return [block]

    # Découpage optimal en segments de 1-2 lignes
    text_segments = _split_text_optimal(text, max_chars_per_line, max_lines)

    if len(text_segments) <= 1:
        return [block]

    # Parser le timing
    try:
        start_str, end_str = block["timecode"].split(" --> ")
        start_s = _parse_time_to_seconds(start_str)
        end_s = _parse_time_to_seconds(end_str)
    except (ValueError, IndexError):
        return [block]

    total_duration = max(end_s - start_s, min_duration_s * len(text_segments))
    weights = _calculate_duration_weights(text_segments)

    sub_blocks: List[Dict[str, str]] = []
    current_time = start_s

    for i, segment_text in enumerate(text_segments):
        if not segment_text.strip():
            continue

        weight = weights[i] if i < len(weights) else 1.0 / max(1, len(text_segments))
        seg_duration = max(total_duration * weight, min_duration_s)

        seg_end = min(current_time + seg_duration, end_s)

        # Léger overlap avec le sous-bloc suivant, sauf pour le dernier
        if i < len(text_segments) - 1:
            seg_end = min(seg_end + overlap_s, end_s)

        seg_end = max(seg_end, current_time + min_duration_s)
        seg_end = min(seg_end, end_s)

        timecode_line = f"{_to_srt_time(current_time)} --> {_to_srt_time(seg_end)}"

        sub_blocks.append(
            {
                "index": str(len(sub_blocks) + 1),
                "timecode": timecode_line,
                "text": segment_text,
            }
        )

        current_time = seg_end

    # Si un seul sous-bloc a été créé, retourner l'original
    if len(sub_blocks) <= 1:
        return [block]

    return sub_blocks


# ─── Post-processing ────────────────────────────────────────────────────────


def _post_process_gaps(
    blocks: List[Dict[str, str]],
    max_gap_s: float = 0.03,
) -> List[Dict[str, str]]:
    """
    Supprime les écrans noirs entre segments consécutifs.

    Si deux segments se suivent avec un gap > max_gap_s, on étend la fin
    du premier segment pour réduire le gap à max_gap_s.
    """
    if len(blocks) <= 1:
        return blocks

    result: List[Dict[str, str]] = []
    for i in range(len(blocks) - 1):
        current = dict(blocks[i])
        next_block = blocks[i + 1]

        _, curr_end = _parse_srt_timecode(current["timecode"])
        next_start, _ = _parse_srt_timecode(next_block["timecode"])

        gap = next_start - curr_end

        # Si gap trop grand (> max_gap_s), étendre le segment courant
        if gap > max_gap_s:
            curr_start, _ = _parse_srt_timecode(current["timecode"])
            new_end = next_start - max_gap_s
            # Ne pas étendre au-delà du début du segment courant
            if new_end > curr_start:
                current["timecode"] = (
                    f"{_to_srt_time(curr_start)} --> {_to_srt_time(new_end)}"
                )

        result.append(current)

    # Ajouter le dernier bloc inchangé
    result.append(blocks[-1])

    return result


def _merge_short_segments(
    blocks: List[Dict[str, str]],
    min_duration_s: float = 0.5,
    max_chars_per_line: int = 42,
) -> List[Dict[str, str]]:
    """
    Fusionne les segments trop courts (< min_duration_s) avec leur voisin.

    Amélioration V2 : le texte fusionné est nettoyé (pas de " -- ")
    et on vérifie que le résultat ne dépasse pas la limite de caractères.
    """
    if len(blocks) <= 1:
        return blocks

    result: List[Dict[str, str]] = []
    i = 0
    while i < len(blocks):
        block = dict(blocks[i])
        start, end = _parse_srt_timecode(block["timecode"])
        duration = end - start

        # Segment trop court : fusionner avec le suivant
        if duration < min_duration_s and i < len(blocks) - 1:
            next_block = blocks[i + 1]
            next_start, next_end = _parse_srt_timecode(next_block["timecode"])

            # Texte fusionné proprement
            merged_text = f"{block['text']}\n{next_block['text']}"

            # Vérifier que le texte fusionné ne dépasse pas la limite raisonnable
            clean_merged = _strip_styles(merged_text)
            if len(clean_merged) <= max_chars_per_line * 3:
                # Créer un bloc fusionné
                merged = {
                    "index": next_block["index"],
                    "timecode": next_block["timecode"],
                    "text": merged_text,
                }
                blocks[i + 1] = merged
                i += 1  # Skip le bloc court (fusionné)
                continue

        result.append(block)
        i += 1

    return result


# ─── Point d'entrée principal ───────────────────────────────────────────────


def split_srt_advanced(
    srt_content: str,
    max_chars_per_line: int | None = None,
    max_lines: int = 2,
    min_duration_s: float = 0.7,
    min_segment_duration_s: float = 0.5,
    max_gap_s: float = 0.03,
    overlap_s: float = 0.04,
    resolution: Tuple[int, int] | None = None,
) -> str:
    """
    Point d'entrée principal : découpe un SRT complet par caractères/lignes.

    Si resolution est fourni, max_chars_per_line est automatiquement adapté.
    Si max_chars_per_line est fourni explicitement, il a priorité sur resolution.

    Post-processing automatique :
    1. Chevauchement minimal (overlap_s) entre sous-blocs d'un même bloc parent
    2. Réduction des gaps entre segments consécutifs (max_gap_s)
    3. Fusion des segments trop courts (< min_segment_duration_s)

    Args:
        srt_content: Contenu SRT à découper
        max_chars_per_line: Nombre max de caractères par ligne (auto si None + resolution)
        max_lines: Nombre max de lignes par segment (default: 2)
        min_duration_s: Durée minimale en secondes pour un sous-segment
        min_segment_duration_s: Durée minimale pour qu'un segment survive
        max_gap_s: Gap maximum entre segments consécutifs
        overlap_s: Chevauchement entre sous-blocs d'un même bloc
        resolution: Tuple (largeur, hauteur) de la vidéo pour adaptation auto

    Returns:
        SRT découpé avec index renumérotés, ou SRT original si pas de découpage
    """
    # Résolution → chars par ligne
    if max_chars_per_line is None:
        if resolution:
            max_chars_per_line = get_max_chars_for_resolution(*resolution)
        else:
            max_chars_per_line = DEFAULT_MAX_CHARS_PER_LINE

    # Pas de contenu ou désactivé
    if not srt_content or max_chars_per_line <= 0 or max_lines <= 0:
        return srt_content

    blocks = _parse_srt(srt_content)
    if not blocks:
        return srt_content

    new_blocks: List[Dict[str, str]] = []

    for block in blocks:
        text = block.get("text", "").strip()
        if not text:
            continue

        # Calculer la longeur "propre" sans styles
        clean_text = _strip_styles(text)

        # Découper si nécessaire : dépasse max_chars * max_lines
        max_chars_total = max_chars_per_line * max_lines
        if len(clean_text) > max_chars_total or _count_words(text) > 10:
            splitted = _split_single_block_v2(
                block,
                max_chars_per_line=max_chars_per_line,
                max_lines=max_lines,
                min_duration_s=min_duration_s,
                overlap_s=overlap_s,
            )
            new_blocks.extend(splitted)
        else:
            new_blocks.append(block)

    # Post-processing : réduire les gaps entre segments
    new_blocks = _post_process_gaps(new_blocks, max_gap_s=max_gap_s)

    # Post-processing : fusionner les segments trop courts
    new_blocks = _merge_short_segments(
        new_blocks,
        min_duration_s=min_segment_duration_s,
        max_chars_per_line=max_chars_per_line,
    )

    # Réécrire le SRT avec index séquentiels
    return _write_srt(new_blocks)


# ─── Alias de compatibilité ─────────────────────────────────────────────────


def split_srt_by_words(
    srt_content: str,
    max_words_per_segment: int = 6,
    min_duration_s: float = 0.8,
    min_segment_duration_s: float = 0.5,
    max_gap_s: float = 0.03,
    overlap_s: float = 0.05,
) -> str:
    """
    Ancien point d'entrée (compatibilité).
    Délègue à split_srt_advanced avec max_chars = max_words * ~7 (estimation).
    max_words=15 → ~105 chars → ~2.5 lignes → équivalent à l'ancien comportement.
    """
    # Conversion grossière mots → chars (~7 chars/mot en moyenne)
    est_chars = max_words_per_segment * 7 if max_words_per_segment > 0 else 0
    if max_words_per_segment <= 0:
        return srt_content

    return split_srt_advanced(
        srt_content,
        max_chars_per_line=est_chars // 2,  # ~2 lignes
        min_duration_s=min_duration_s,
        min_segment_duration_s=min_segment_duration_s,
        max_gap_s=max_gap_s,
        overlap_s=overlap_s,
    )
