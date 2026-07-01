"""
pipeline/meta_analysis.py — Analyse des métadonnées vidéo — Subvox

MetaAnalysisStep : première étape d'analyse, exécutée juste après le download.

Analyse le titre, la description et la durée de la vidéo via OpenRouter DeepSeek V3.1
pour déterminer :
- Catégorie de contenu (interview, podcast, vlog, tutorial, news, ...)
- Type de contenu (conversation, screencast, live, ...)
- Langue probable
- Si la vidéo nécessite de l'anonymisation (visages/plaques)
- Recommandations de floutage

Règles d'anonymisation : 12 catégories avec config faces/plates pré-définie.
"""

from __future__ import annotations

import json

from core.logging_setup import get_logger
from core.openrouter import call_openrouter, PRIMARY_MODEL
from core.pipeline.analysis_base import AnalysisStep

logger = get_logger(__name__)


# ─── Règles de floutage par catégorie ───────────────────────────────────────
# Chaque catégorie définit si le floutage des visages et/ou des plaques
# doit être activé par défaut.

ANONYMIZATION_RULES: dict[str, dict[str, bool]] = {
    "interview":     {"faces": True,  "plates": False},
    "podcast":       {"faces": False, "plates": False},  # audio only
    "vlog":          {"faces": True,  "plates": True},   # rue, conduite
    "tutorial":      {"faces": False, "plates": False},  # screencast
    "news":          {"faces": True,  "plates": True},
    "entertainment": {"faces": False, "plates": False},
    "gaming":        {"faces": False, "plates": False},
    "sports":        {"faces": True,  "plates": False},
    "music":         {"faces": False, "plates": False},
    "vehicule":      {"faces": True,  "plates": True},   # dashcam, review auto
    "surveillance":  {"faces": True,  "plates": True},
    "other":         {"faces": True,  "plates": True},   # par défaut : prudent
}

DEFAULT_RULE = {"faces": True, "plates": True}


def _get_anonymization_rule(category: str) -> dict[str, bool]:
    """Retourne la règle de floutage pour une catégorie donnée."""
    return ANONYMIZATION_RULES.get(category, DEFAULT_RULE)


# ─── Prompt système ─────────────────────────────────────────────────────────

META_ANALYSIS_SYSTEM_PROMPT = """Tu es un expert en analyse de métadonnées vidéo.
À partir du titre, de la description et de la durée, tu détermines :
1. La catégorie de contenu (interview, podcast, vlog, tutorial, news, entertainment, gaming, sports, music, vehicule, surveillance, other)
2. Le type de contenu (conversation, screencast, live, presentation, documentary, vlog, tutorial, review, sport_event, music_video, other)
3. La langue probable (code ISO 639-1, ou "unknown")
4. Si la vidéo contient probablement des visages humains (bool)
5. Si la vidéo contient probablement des plaques d'immatriculation (bool)
6. Si la vidéo contient du texte superposé (slides, titres) (bool)
7. Si la vidéo a été filmée en extérieur (bool)
8. Le ton estimé (professional, educational, casual, humorous, serious, emotional, neutral)
9. Le public cible estimé (developers, general, children, professionals, students, researchers, other)

Réponds UNIQUEMENT avec un JSON valide, sans commentaire."""


META_ANALYSIS_USER_TEMPLATE = """Titre : {title}
Description : {description}
Durée : {duration_s} secondes ({duration_min} minutes)

Analyse ces métadonnées et retourne un JSON avec les champs :
- category (str)
- sub_category (str)
- content_type (str)
- language_guess (str, code ISO 639-1)
- language_confidence (float, 0-1)
- estimated_tone (str)
- target_audience (str)
- needs_anonymization (bool)
- likely_has_faces (bool)
- likely_has_text_overlay (bool)
- likely_outdoor (bool)
- confidence_explanation (str courte, 1 phrase)"""


# ─── Step ───────────────────────────────────────────────────────────────────


class MetaAnalysisStep(AnalysisStep):
    """
    Analyse les métadonnées vidéo via OpenRouter DeepSeek V3.1.

    Input :
        title (str) — Titre de la vidéo
        description (str) — Description de la vidéo
        duration_s (number) — Durée en secondes

    Output :
        category, sub_category, content_type, language_guess,
        language_confidence, estimated_tone, target_audience,
        needs_anonymization, likely_has_faces, likely_has_text_overlay,
        likely_outdoor
    """

    async def analyze(self, input_data: dict) -> dict:
        title = input_data.get("title", "")
        description = input_data.get("description", "")
        duration_s = float(input_data.get("duration_s", 0))
        duration_min = round(duration_s / 60, 1)

        # Validation rapide
        if not title and not description:
            logger.warning(
                "MetaAnalysisStep: titre et description vides — utilisation défauts",
            )
            return self._default_result(duration_s)

        # Construction du message utilisateur
        user_prompt = META_ANALYSIS_USER_TEMPLATE.format(
            title=title or "(aucun titre)",
            description=(description or "(aucune description)")[:2000],
            duration_s=duration_s,
            duration_min=duration_min,
        )

        try:
            raw_response = await call_openrouter(
                messages=[
                    {"role": "system", "content": META_ANALYSIS_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                model=PRIMARY_MODEL,
                temperature=0.3,
                max_tokens=1024,
                user_id=input_data.get("user_id", "anonymous"),
                cache_key=f"meta_analysis|{title[:100]}|{description[:200]}|{duration_s}",
            )
            # call_openrouter retourne (content | None, tokens_in, tokens_out)
            result_text = raw_response[0] if isinstance(raw_response, tuple) else raw_response

            if not result_text:
                logger.warning("MetaAnalysisStep: réponse OpenRouter vide — fallback")
                return self._default_result(duration_s)

            # Parser le JSON de la réponse
            analysis = self._parse_response(result_text, duration_s)
            logger.info(
                "MetaAnalysis terminée",
                extra={
                    "category": analysis.get("category", "other"),
                    "needs_anonymization": analysis.get("needs_anonymization", True),
                    "language_guess": analysis.get("language_guess", "unknown"),
                },
            )
            return analysis

        except Exception as exc:
            logger.error(
                "MetaAnalysisStep échouée — fallback vers valeurs par défaut",
                extra={"error": str(exc)},
            )
            return self._default_result(duration_s)

    def _parse_response(self, text: str, duration_s: float) -> dict:
        """Parse la réponse JSON d'OpenRouter, fallback vers défauts si invalide."""
        try:
            # Nettoyer la réponse — parfois OpenRouter ajoute du texte avant/après le JSON
            cleaned = text.strip()
            if "```json" in cleaned:
                cleaned = cleaned.split("```json")[1].split("```")[0].strip()
            elif "```" in cleaned:
                cleaned = cleaned.split("```")[1].split("```")[0].strip()

            analysis = json.loads(cleaned)
        except (json.JSONDecodeError, IndexError, TypeError):
            logger.warning(
                "MetaAnalysisStep: réponse JSON invalide — utilisation défauts",
                extra={"response_preview": text[:300]},
            )
            return self._default_result(duration_s)

        # Fusionner avec les règles d'anonymisation
        category = analysis.get("category", "other")
        rule = _get_anonymization_rule(category)
        analysis["recommended_anonymization"] = rule

        # Calculer la duration_category
        d = duration_s
        if d <= 120:
            analysis["duration_category"] = "short"
        elif d <= 300:
            analysis["duration_category"] = "medium"
        elif d <= 900:
            analysis["duration_category"] = "long"
        else:
            analysis["duration_category"] = "xlong"

        # S'assurer que tous les champs clés sont présents
        defaults = self._default_result(duration_s)
        for key, value in defaults.items():
            if key not in analysis:
                analysis[key] = value

        return analysis

    def _default_result(self, duration_s: float) -> dict:
        """Valeurs par défaut si l'analyse échoue."""
        d = duration_s
        if d <= 120:
            duration_cat = "short"
        elif d <= 300:
            duration_cat = "medium"
        elif d <= 900:
            duration_cat = "long"
        else:
            duration_cat = "xlong"

        return {
            "category": "other",
            "sub_category": "",
            "content_type": "other",
            "language_guess": "unknown",
            "language_confidence": 0.0,
            "duration_category": duration_cat,
            "estimated_tone": "neutral",
            "target_audience": "general",
            "needs_anonymization": True,
            "recommended_anonymization": {"faces": True, "plates": True},
            "likely_has_faces": True,
            "likely_has_text_overlay": False,
            "likely_outdoor": False,
        }

    def get_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Titre de la vidéo"},
                "description": {"type": "string", "description": "Description de la vidéo"},
                "duration_s": {
                    "type": "number",
                    "description": "Durée de la vidéo en secondes",
                },
                "user_id": {
                    "type": "string",
                    "description": "ID utilisateur pour le tracking OpenRouter",
                },
            },
            "required": ["title", "duration_s"],
        }