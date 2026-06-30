"""
pipeline/text_analysis.py — Analyse textuelle du transcript — Subvox

TextAnalysisStep : analyse le transcript complet via OpenRouter DeepSeek V3.1
pour extraire :
- Thèmes principaux
- Tonalité générale
- Moments forts (highlights avec timestamps)
- Mots-clés
- Entités nommées (personnes, organisations, lieux, produits)
- Complexité linguistique
- Sponsoring / call-to-action

Gère le chunking pour les longs transcripts (Tier 2/3).
"""

from __future__ import annotations

import json
import re
from typing import Any

from core.logging_setup import get_logger
from core.openrouter import call_openrouter, PRIMARY_MODEL
from core.pipeline.analysis_base import AnalysisStep

logger = get_logger(__name__)


# ─── Constantes de chunking ─────────────────────────────────────────────────

# Au-delà de ~8000 tokens, on chunke le transcript
TRANSCRIPT_CHUNK_THRESHOLD = 15000  # caractères
MAX_CHUNK_SIZE = 12000  # caractères par chunk


# ─── Prompts ────────────────────────────────────────────────────────────────

TEXT_ANALYSIS_SYSTEM_PROMPT = """Tu es un expert en analyse textuelle de transcripts vidéo.
À partir d'un transcript complet, tu extrais des informations structurées.

Règles :
- Sois précis et factuel
- Les timestamps doivent correspondre exactement au format SRT (HH:MM:SS,mmm)
- Les highlights doivent être des moments vraiment importants (pas du remplissage)
- Détecte le sponsoring et les calls-to-action
- Identifie les interlocuteurs distincts par leur style/ton"""


TEXT_ANALYSIS_USER_TEMPLATE = """Titre de la vidéo : {title}
Description : {description}
Transcript complet :
```
{transcript}
```

Analyse ce transcript et retourne un JSON avec les champs suivants :
- themes (array of strings) : thèmes principaux abordés
- tone (string) : tonalité générale (educational, professional, casual, humorous, serious, emotional, neutral, persuasive, inspirational)
- speaker_count_estimate (integer) : estimation du nombre d'interlocuteurs distincts (entre 1 et 10)
- highlights (array of objects) : moments forts avec :
  - timestamp_s (float) : début du moment fort en secondes
  - end_s (float) : fin du moment fort en secondes
  - label (string) : description courte du moment
  - importance (string) : "critical", "high", "medium", "low"
- keywords (array of strings) : mots-clés pertinents (max 15)
- named_entities (object) : entités nommées avec :
  - people (array of strings)
  - organizations (array of strings)
  - locations (array of strings)
  - products (array of strings)
- language_complexity (string) : "beginner", "intermediate", "advanced", "expert"
- has_sponsorship (boolean) : true si sponsoring/promo détecté
- has_call_to_action (boolean) : true si call-to-action détecté (like, subscribe, follow)
- transcript_summary (string) : résumé de 2-3 phrases du contenu"""


# ─── Helpers de chunking ────────────────────────────────────────────────────


def _chunk_transcript(transcript: str) -> list[str]:
    """Découpe un long transcript en chunks de taille raisonnable."""
    if len(transcript) <= TRANSCRIPT_CHUNK_THRESHOLD:
        return [transcript]

    chunks: list[str] = []
    lines = transcript.split("\n")
    current_chunk: list[str] = []
    current_size = 0

    for line in lines:
        line_len = len(line) + 1  # +1 pour le newline
        if current_size + line_len > MAX_CHUNK_SIZE and current_chunk:
            chunks.append("\n".join(current_chunk))
            current_chunk = [line]
            current_size = line_len
        else:
            current_chunk.append(line)
            current_size += line_len

    if current_chunk:
        chunks.append("\n".join(current_chunk))

    return chunks


def _extract_timestamps(transcript: str) -> list[dict]:
    """Extrait les timestamps du transcript SRT pour référence."""
    timestamps: list[dict] = []
    pattern = r"(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})"

    for match in re.finditer(pattern, transcript):
        start_str = match.group(1)
        end_str = match.group(2)
        # Convertir en secondes
        h, m, s, ms = 0, 0, 0, 0
        parts = start_str.replace(",", ".").split(":")
        start_s = float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
        parts = end_str.replace(",", ".").split(":")
        end_s = float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
        timestamps.append({"start_s": start_s, "end_s": end_s})

    return timestamps


# ─── Step ────────────────────────────────────────────────────────────────────


class TextAnalysisStep(AnalysisStep):
    """
    Analyse textuelle du transcript vidéo via OpenRouter DeepSeek V3.1.

    Input :
        transcript (str) — Transcript complet de la vidéo (format SRT ou texte brut)
        title (str) — Titre de la vidéo
        description (str) — Description de la vidéo

    Output :
        themes, tone, speaker_count_estimate, highlights, keywords,
        named_entities, language_complexity, has_sponsorship,
        has_call_to_action, transcript_summary, chunk_count
    """

    async def analyze(self, input_data: dict) -> dict:
        transcript = input_data.get("transcript", "")
        title = input_data.get("title", "")
        description = input_data.get("description", "")
        user_id = input_data.get("user_id", "anonymous")

        if not transcript:
            logger.warning("TextAnalysisStep: transcript vide — utilisation défauts")
            return self._default_result()

        # Chunking si nécessaire
        chunks = _chunk_transcript(transcript)
        chunk_count = len(chunks)

        if chunk_count == 1:
            # Analyse simple
            return await self._analyze_single(
                transcript, title, description, user_id
            )
        else:
            # Analyse multi-chunks avec fusion
            return await self._analyze_multi_chunk(
                chunks, title, description, user_id, transcript
            )

    async def _analyze_single(
        self, transcript: str, title: str, description: str, user_id: str
    ) -> dict:
        """Analyse un transcript qui tient dans un seul appel OpenRouter."""
        truncated = transcript[:30000]  # Sécurité : max 30k chars
        user_prompt = TEXT_ANALYSIS_USER_TEMPLATE.format(
            title=title or "(inconnu)",
            description=(description or "")[:1000],
            transcript=truncated,
        )

        try:
            raw_response = await call_openrouter(
                messages=[
                    {"role": "system", "content": TEXT_ANALYSIS_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                model=PRIMARY_MODEL,
                temperature=0.3,
                max_tokens=4096,
                user_id=user_id,
                cache_key=f"text_analysis|{title[:100]}|{len(transcript)}",
            )
            # call_openrouter retourne (content | None, tokens_in, tokens_out)
            result_text = raw_response[0] if isinstance(raw_response, tuple) else raw_response

            if not result_text:
                logger.warning("TextAnalysisStep: réponse OpenRouter vide — fallback")
                return self._default_result()

            result = self._parse_response(result_text)
            result["chunk_count"] = 1

            logger.info(
                "TextAnalysis terminée (single)",
                extra={
                    "themes": len(result.get("themes", [])),
                    "highlights": len(result.get("highlights", [])),
                    "keywords": len(result.get("keywords", [])),
                },
            )
            return result

        except Exception as exc:
            logger.error(
                "TextAnalysisStep échouée — fallback vers défauts",
                extra={"error": str(exc)},
            )
            return self._default_result()

    async def _analyze_multi_chunk(
        self,
        chunks: list[str],
        title: str,
        description: str,
        user_id: str,
        full_transcript: str,
    ) -> dict:
        """Analyse multi-chunks : chaque chunk est analysé indépendamment, puis fusion."""
        logger.info(
            "TextAnalysis multi-chunks démarrée",
            extra={"chunk_count": len(chunks), "total_chars": sum(len(c) for c in chunks)},
        )

        # Analyser chaque chunk
        chunk_results: list[dict] = []
        for i, chunk in enumerate(chunks):
            try:
                result = await self._analyze_single(chunk, f"{title} (partie {i+1})", description, user_id)
                chunk_results.append(result)
            except Exception as exc:
                logger.warning(
                    f"Échec analyse chunk {i+1}/{len(chunks)}",
                    extra={"error": str(exc)},
                )
                chunk_results.append(self._default_result())

        # Fusionner les résultats
        merged = self._merge_chunk_results(chunk_results, full_transcript)
        merged["chunk_count"] = len(chunks)

        logger.info(
            "TextAnalysis multi-chunks fusionnée",
            extra={
                "chunks": len(chunks),
                "themes": len(merged.get("themes", [])),
                "highlights": len(merged.get("highlights", [])),
            },
        )
        return merged

    def _merge_chunk_results(self, results: list[dict], full_transcript: str) -> dict:
        """Fusionne les résultats de plusieurs chunks."""
        merged: dict = self._default_result()

        # Fusion des thèmes (uniques)
        all_themes: list[str] = []
        for r in results:
            for theme in r.get("themes", []):
                if theme not in all_themes:
                    all_themes.append(theme)
        merged["themes"] = all_themes

        # Fusion des mots-clés (uniques)
        all_keywords: list[str] = []
        for r in results:
            for kw in r.get("keywords", []):
                if kw not in all_keywords:
                    all_keywords.append(kw)
        merged["keywords"] = all_keywords[:15]

        # Fusion des highlights (tous, dédoublonnés par timestamp)
        seen_timestamps: set[tuple] = set()
        all_highlights: list[dict] = []
        for r in results:
            for h in r.get("highlights", []):
                key = (round(h.get("timestamp_s", 0), 1), round(h.get("end_s", 0), 1))
                if key not in seen_timestamps:
                    seen_timestamps.add(key)
                    all_highlights.append(h)
        merged["highlights"] = all_highlights

        # Fusion des entités nommées
        entities: dict = {"people": [], "organizations": [], "locations": [], "products": []}
        for r in results:
            ne = r.get("named_entities", {})
            for category in entities:
                for item in ne.get(category, []):
                    if item not in entities[category]:
                        entities[category].append(item)
        merged["named_entities"] = entities

        # Moyenne du speaker_count (arrondie)
        speaker_counts = [r.get("speaker_count_estimate", 1) for r in results if r.get("speaker_count_estimate")]
        merged["speaker_count_estimate"] = (
            round(sum(speaker_counts) / len(speaker_counts)) if speaker_counts else 1
        )

        # Tone le plus fréquent
        tones = [r.get("tone") for r in results if r.get("tone")]
        if tones:
            merged["tone"] = max(set(tones), key=tones.count)

        # Complexité max
        complexities = ["beginner", "intermediate", "advanced", "expert"]
        max_idx = 0
        for r in results:
            c = r.get("language_complexity", "beginner")
            if c in complexities:
                idx = complexities.index(c)
                if idx > max_idx:
                    max_idx = idx
        merged["language_complexity"] = complexities[max_idx]

        # Sponsoring / CTA : true si au moins un chunk a détecté
        merged["has_sponsorship"] = any(r.get("has_sponsorship") for r in results)
        merged["has_call_to_action"] = any(r.get("has_call_to_action") for r in results)

        # Résumé : prendre le premier chunk
        merged["transcript_summary"] = results[0].get("transcript_summary", "") if results else ""

        return merged

    def _parse_response(self, text: str) -> dict:
        """Parse la réponse JSON d'OpenRouter."""
        try:
            cleaned = text.strip()
            if "```json" in cleaned:
                cleaned = cleaned.split("```json")[1].split("```")[0].strip()
            elif "```" in cleaned:
                cleaned = cleaned.split("```")[1].split("```")[0].strip()

            return json.loads(cleaned)
        except (json.JSONDecodeError, IndexError, TypeError):
            logger.warning(
                "TextAnalysisStep: réponse JSON invalide — utilisation défauts",
                extra={"response_preview": text[:300]},
            )
            return self._default_result()

    def _default_result(self) -> dict:
        return {
            "themes": [],
            "tone": "neutral",
            "speaker_count_estimate": 1,
            "highlights": [],
            "keywords": [],
            "named_entities": {
                "people": [],
                "organizations": [],
                "locations": [],
                "products": [],
            },
            "language_complexity": "beginner",
            "has_sponsorship": False,
            "has_call_to_action": False,
            "transcript_summary": "",
        }

    def get_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "transcript": {
                    "type": "string",
                    "description": "Transcript complet de la vidéo (SRT ou texte brut)",
                },
                "title": {
                    "type": "string",
                    "description": "Titre de la vidéo",
                },
                "description": {
                    "type": "string",
                    "description": "Description de la vidéo",
                },
                "user_id": {
                    "type": "string",
                    "description": "ID utilisateur pour tracking OpenRouter",
                },
            },
            "required": ["transcript"],
        }