"""
srt_chunking.py — Découpage intelligent des SRT pour traduction LLM
"""

import re
from typing import List, Dict, Tuple


def parse_srt_to_blocks(srt_content: str) -> List[Dict[str, str]]:
    """
    Parse un contenu SRT en une liste de blocs.

    Chaque bloc : {
        "index": "1",
        "timecode": "00:00:01,000 --> 00:00:03,000",
        "text": "Bonjour tout le monde",
    }
    """
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


def blocks_to_srt(blocks: List[Dict[str, str]]) -> str:
    """Reconstitue un SRT à partir de blocs."""
    parts = []
    for i, block in enumerate(blocks):
        # On réindexe séquentiellement à partir de 1
        parts.append(f"{i + 1}\n{block['timecode']}\n{block['text']}\n")
    return "\n".join(parts)


def group_blocks_into_chunks(
    blocks: List[Dict[str, str]],
    max_chars: int = 2000,
    max_blocks: int = 15,
) -> List[List[Dict[str, str]]]:
    """
    Groupe les blocs SRT en chunks respectant les limites de taille.

    Stratégie :
    - Ne jamais couper un bloc (garder l'intégralité).
    - Cumuler les caractères jusqu'à dépasser max_chars OU max_blocks.
    - Si on dépasse max_chars, on peut ajouter jusqu'à 1 bloc supplémentaire
      pour terminer une phrase (s'il se termine par . ! ?).
    - Ne pas mélanger les blocs distants (garder l'ordre).
    """
    if not blocks:
        return []

    chunks = []
    current_chunk = []
    current_chars = 0

    for block in blocks:
        block_text = block.get("text", "")
        block_len = len(block_text)
        current_len = current_chars + block_len
        current_count = len(current_chunk)

        # Dépassement des limites
        if current_chars > 0 and (
            current_len > max_chars or current_count >= max_blocks
        ):
            # Coupure non-stricte : si le chunk courant termine une phrase,
            # on coupe maintenant (on n'ajoute pas ce bloc)
            if _ends_with_punctuation(current_chunk[-1]["text"]):
                chunks.append(current_chunk)
                current_chunk = []
                current_chars = 0
            else:
                # Essayer d'ajouter ce bloc pour finir la phrase
                allowed = False
                if _ends_with_punctuation(block_text):
                    # Ce bloc termine la phrase → on l'ajoute même si > max_chars
                    allowed = True
                if not allowed and current_len > max_chars * 1.3:
                    # Trop gros (30% over) → on coupe ici même sans ponctuation
                    allowed = False
                else:
                    allowed = True

                if allowed:
                    current_chunk.append(block)
                    current_chars += block_len
                    chunks.append(current_chunk)
                    current_chunk = []
                    current_chars = 0
                    continue
                else:
                    # Trop gros, on coupe sans ce bloc
                    chunks.append(current_chunk)
                    current_chunk = []
                    current_chars = 0

        current_chunk.append(block)
        current_chars += block_len

    # Ajouter le dernier chunk
    if current_chunk:
        chunks.append(current_chunk)

    return chunks


def _ends_with_punctuation(text: str) -> bool:
    """Vérifie si le texte se termine par une ponctuation de phrase."""
    return bool(re.search(r"[.!?]\s*$", text.strip()))


def chunk_srt_content(
    srt_content: str,
    max_chars: int = 2000,
    max_blocks: int = 15,
) -> Tuple[List[str], List[List[Dict[str, str]]]]:
    """
    Découpe un SRT en plusieurs chunks.

    Retourne :
        - liste des SRT chunkés (chaque chunk est un SRT complet)
        - liste des blocs par chunk (pour debug)
    """
    blocks = parse_srt_to_blocks(srt_content)
    chunked_blocks = group_blocks_into_chunks(blocks, max_chars, max_blocks)

    srt_chunks = []
    for chunk in chunked_blocks:
        srt_chunks.append(blocks_to_srt(chunk))

    return srt_chunks, chunked_blocks


def should_chunk_srt(
    char_count: int, block_count: int, max_chars: int = 8000, max_blocks: int = 100
) -> bool:
    """
    Determine si un SRT doit etre decoupe en chunks pour la traduction LLM.

    Retourne True si le nombre de caracteres ou de blocs depasse les seuils.
    """
    return char_count > max_chars or block_count > max_blocks


def chunk_srt(
    srt_content: str, max_chars: int = 8000, max_blocks: int = 60
) -> list[str]:
    """
    Decoupe un SRT en plusieurs chunks pour la traduction LLM.

    Retourne une liste de strings SRT, chaque chunk etant un SRT complet
    avec ses propres index.
    """
    chunks, _ = chunk_srt_content(
        srt_content, max_chars=max_chars, max_blocks=max_blocks
    )
    return chunks


def merge_srt_chunks(chunks: list[str]) -> str:
    """
    Fusionne plusieurs SRT chunkés en un seul SRT final.

    Les index sont réordonnés séquentiellement.
    """
    all_blocks = []
    for chunk in chunks:
        all_blocks.extend(parse_srt_to_blocks(chunk))
    return blocks_to_srt(all_blocks)


# ── Détection de coupure naturelle (phrase) ───────────────────────────────


def _ends_with_punctuation(text: str) -> bool:
    """Vérifie si le texte se termine par une ponctuation de phrase."""
    return bool(re.search(r"[.!?]\s*$", text.strip()))


def find_natural_break(blocks: List[Dict[str, str]], max_lookahead: int = 3) -> int:
    """
    Trouve un point de coupure naturel dans une liste de blocs.

    Recherche la première fin de phrase dans les `max_lookahead` blocs suivants.
    Retourne l'indice du bloc (exclusif) à couper, ou -1 si pas trouvé.
    """
    for i in range(min(max_lookahead, len(blocks))):
        if _ends_with_punctuation(blocks[i]["text"]):
            return i + 1
    return -1
