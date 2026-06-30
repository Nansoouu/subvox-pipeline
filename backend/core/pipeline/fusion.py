"""
pipeline/fusion.py — Fusion des analyses vidéo — Subvox

FusionStep : dernière étape d'analyse, combine les résultats des 5 étapes
précédentes (meta, text, visual, anonymization, speakers) en un résumé
global enrichi via OpenRouter DeepSeek V3.1.

Produit :
  - Résumé global enrichi
  - Tags unifiés (SEO, catégories, mots-clés)
  - Score qualité (0-1)
  - Suggestions SEO (titre, description optimisés)
  - Coût total estimé des analyses

Stocké dans jobs.analysis_result.fusion
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from core.config import settings
from core.logging_setup import get_logger
from core.openrouter import call_openrouter, PRIMARY_MODEL
from core.pipeline.analysis_base import AnalysisStep

logger = get_logger(__name__)

# ─── Prompt système ─────────────────────────────────────────────────────────

FUSION_SYSTEM_PROMPT = """Tu es un expert en analyse vidéo et SEO.
Tu reçois les résultats de 5 analyses d'une même vidéo :
1. Analyse des métadonnées (catégorie, type, langue, anonymisation)
2. Analyse du transcript (thèmes, tonalité, highlights, mots-clés)
3. Analyse visuelle (scènes, objets, visages détectés)
4. Anonymisation (visages/plaques floutés)
5. Analyse des locuteurs (speakers, temps de parole)

Ta mission : produire un résumé global enrichi en français.

Réponds UNIQUEMENT avec un JSON valide, sans commentaire autour."""


FUSION_USER_TEMPLATE = """Voici les 5 analyses d'une vidéo :

=== 1. MÉTADONNÉES ===
{meta_json}

=== 2. ANALYSE TEXTUELLE ===
{text_json}

=== 3. ANALYSE VISUELLE ===
{visual_json}

=== 4. ANONYMISATION ===
{anonymization_json}

=== 5. LOCUTEURS ===
{speakers_json}

Génère un JSON avec les champs suivants :

{{
  "global_summary": "Résumé enrichi en français (3-5 phrases) qui synthétise le contenu, le contexte visuel et les intervenants",
  "tags": ["tag1", "tag2", ...],  // 8-15 tags unifiés (SEO) combinant catégories, thèmes, sujets
  "quality_score": 0.85,  // Score de qualité global (0.0-1.0) basé sur la complétude de l'analyse
  "missing_analyses": [],  // Listes des analyses manquantes (si certaines étapes sont vides)
  "seo": {{
    "suggested_title": "Titre optimisé SEO (max 60 chars)",
    "suggested_description": "Description optimisée SEO (max 160 chars)",
    "seo_keywords": ["mot-clé1", "mot-clé2", ...]  // 5-10 mots-clés SEO
  }},
  "content_insights": {{
    "main_topic": "Sujet principal de la vidéo",
    "complexity": "beginner|intermediate|advanced",
    "has_multiple_speakers": true/false,
    "has_visual_content": true/false,
    "needs_anonymization": true/false,
    "estimated_audience": "public cible estimé"
  }}
}}

Si une analyse est vide, mets "non disponible" dans le résumé et ajoute-la dans missing_analyses."""


class FusionStep(AnalysisStep):
    """
    Fusionne les 5 analyses en un résumé global enrichi via DeepSeek V3.1.

    Input :
        meta_analysis (dict) — Résultat de MetaAnalysisStep
        text_analysis (dict) — Résultat de TextAnalysisStep
        visual_analysis (dict) — Résultat de VisualAnalysisStep
        anonymization (dict) — Résultat de AnonymizationStep
        speakers (dict) — Résultat de SpeakerAnalysisStep
        job_id (str) — ID du job

    Output :
        global_summary (str) — Résumé enrichi en français
        tags (list) — Tags unifiés SEO
        quality_score (float) — Score qualité 0-1
        seo (dict) — Suggestions SEO
        content_insights (dict) — Insights structurés
        missing_analyses (list) — Analyses manquantes
        cost_total_usd (float) — Coût estimé total
        generated_at (str) — Timestamp ISO
        models_used (list) — Modèles utilisés
    """

    async def analyze(self, input_data: dict) -> dict:
        meta = input_data.get("meta_analysis", {}) or {}
        text = input_data.get("text_analysis", {}) or {}
        visual = input_data.get("visual_analysis", {}) or {}
        anonymization = input_data.get("anonymization", {}) or {}
        speakers = input_data.get("speakers", {}) or {}
        job_id = input_data.get("job_id", "unknown")

        log_extra = {"job_id": job_id[:8] if len(job_id) > 8 else job_id}

        logger.info(
            "Démarrage fusion des analyses",
            extra={
                "meta": bool(meta),
                "text": bool(text),
                "visual": bool(visual),
                "anonymization": bool(anonymization),
                "speakers": bool(speakers),
                **log_extra,
            },
        )

        import time as _time
        start = _time.time()

        # Détecter les analyses manquantes
        missing = []
        if not meta or meta.get("category", "other") == "other" and not meta.get("sub_category"):
            missing.append("meta_analysis")
        if not text or not text.get("themes"):
            missing.append("text_analysis")
        if not visual or not visual.get("scenes"):
            missing.append("visual_analysis")
        if not anonymization or anonymization.get("mode") == "disabled":
            missing.append("anonymization")
        if not speakers or not speakers.get("speakers"):
            missing.append("speakers")

        # Si toutes les analyses sont manquantes, retourner un fallback
        if len(missing) >= 4:
            logger.warning(
                "Fusion: trop d'analyses manquantes — fallback",
                extra={"missing": missing, **log_extra},
            )
            return self._fallback_result(
                meta=meta,
                text=text,
                visual=visual,
                anonymization=anonymization,
                speakers=speakers,
                missing=missing,
            )

        try:
            # Construire le prompt utilisateur
            user_prompt = FUSION_USER_TEMPLATE.format(
                meta_json=json.dumps(meta, indent=2, ensure_ascii=False)[:2000],
                text_json=json.dumps(text, indent=2, ensure_ascii=False)[:2000],
                visual_json=json.dumps(visual, indent=2, ensure_ascii=False)[:2000],
                anonymization_json=json.dumps(anonymization, indent=2, ensure_ascii=False)[:1500],
                speakers_json=json.dumps(speakers, indent=2, ensure_ascii=False)[:1500],
            )

            raw_response = await call_openrouter(
                messages=[
                    {"role": "system", "content": FUSION_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                model=PRIMARY_MODEL,
                temperature=0.3,
                max_tokens=2048,
                user_id=input_data.get("user_id", f"job_{job_id}"),
                cache_key=f"fusion|{job_id[:16]}|{len(missing)}",
            )
            # call_openrouter retourne (content | None, tokens_in, tokens_out)
            result_text = raw_response[0] if isinstance(raw_response, tuple) else raw_response

            if not result_text:
                logger.warning("FusionStep: réponse OpenRouter vide — fallback")
                return self._default_fallback(missing)

            analysis = self._parse_response(result_text, missing)

            # Ajouter les métadonnées
            analysis["generated_at"] = datetime.now(timezone.utc).isoformat()
            analysis["models_used"] = [PRIMARY_MODEL]
            analysis["cost_total_usd"] = self._estimate_cost(analysis)
            analysis["missing_analyses"] = missing
            analysis["duration_s"] = round(_time.time() - start, 2)

            logger.info(
                "Fusion terminée",
                extra={
                    "score": analysis.get("quality_score", 0),
                    "tags": len(analysis.get("tags", [])),
                    "missing": missing,
                    "duration_s": analysis["duration_s"],
                    **log_extra,
                },
            )
            return analysis

        except Exception as exc:
            logger.error(
                "Fusion échouée — fallback vers valeurs par défaut",
                extra={"error": str(exc), **log_extra},
            )
            result = self._fallback_result(
                meta=meta,
                text=text,
                visual=visual,
                anonymization=anonymization,
                speakers=speakers,
                missing=missing,
            )
            result["duration_s"] = round(_time.time() - start, 2)
            return result

    def _parse_response(self, text: str, missing: list[str]) -> dict:
        """Parse la réponse JSON d'OpenRouter, fallback si invalide."""
        try:
            cleaned = text.strip()
            if "```json" in cleaned:
                cleaned = cleaned.split("```json")[1].split("```")[0].strip()
            elif "```" in cleaned:
                cleaned = cleaned.split("```")[1].split("```")[0].strip()

            result = json.loads(cleaned)
        except (json.JSONDecodeError, IndexError, TypeError):
            logger.warning(
                "Fusion: réponse JSON invalide — fallback",
                extra={"response_preview": text[:300]},
            )
            return {
                "global_summary": "Analyse vidéo complétée.",
                "tags": [],
                "quality_score": 0.5,
                "seo": {
                    "suggested_title": "",
                    "suggested_description": "",
                    "seo_keywords": [],
                },
                "content_insights": {
                    "main_topic": "",
                    "complexity": "intermediate",
                    "has_multiple_speakers": False,
                    "has_visual_content": True,
                    "needs_anonymization": True,
                    "estimated_audience": "general",
                },
            }

        # Normaliser les champs
        if "content_insights" not in result:
            result["content_insights"] = {
                "main_topic": result.get("main_topic", ""),
                "complexity": "intermediate",
                "has_multiple_speakers": False,
                "has_visual_content": True,
                "needs_anonymization": True,
                "estimated_audience": "general",
            }

        if "seo" not in result:
            result["seo"] = {
                "suggested_title": "",
                "suggested_description": "",
                "seo_keywords": result.get("seo_keywords", []),
            }

        return result

    def _fallback_result(
        self,
        meta: dict,
        text: dict,
        visual: dict,
        anonymization: dict,
        speakers: dict,
        missing: list[str],
    ) -> dict:
        """Génère un résultat fallback sans appel API."""
        # Construire un résumé basique à partir des données disponibles
        parts = []

        if meta and meta.get("category"):
            parts.append(
                f"Vidéo de catégorie '{meta.get('category', 'inconnue')}'"
                f" ({meta.get('content_type', 'type inconnu')})."
            )
        if text and text.get("themes"):
            themes = text.get("themes", [])[:3]
            parts.append(f"Thèmes abordés : {', '.join(themes)}.")
        if visual and visual.get("scene_count", 0) > 0:
            parts.append(
                f"Analyse visuelle : {visual.get('scene_count', 0)} scènes détectées,"
                f" {visual.get('global_faces_count', 0)} visages."
            )
        if speakers and speakers.get("total_speakers", 0) > 0:
            parts.append(
                f"{speakers.get('total_speakers', 0)} locuteur(s) identifié(s)."
            )

        if not parts:
            parts.append("Analyse vidéo complétée.")

        # Tags basiques
        tags = []
        if meta and meta.get("category"):
            tags.append(meta["category"])
        if text and text.get("themes"):
            tags.extend(text["themes"][:5])
        if visual and visual.get("visual_tags"):
            tags.extend(visual.get("visual_tags", [])[:5])
        tags = list(dict.fromkeys(tags))[:15]  # Dédupliquer + limiter

        score = max(0.3, 1.0 - (len(missing) * 0.15))

        return {
            "global_summary": " ".join(parts),
            "tags": tags,
            "quality_score": round(score, 2),
            "seo": {
                "suggested_title": meta.get("category", "Vidéo") if meta else "Vidéo",
                "suggested_description": parts[0] if parts else "",
                "seo_keywords": tags[:5],
            },
            "content_insights": {
                "main_topic": text.get("themes", [None])[0] if text and text.get("themes") else "",
                "complexity": "intermediate",
                "has_multiple_speakers": speakers.get("total_speakers", 0) > 1 if speakers else False,
                "has_visual_content": visual.get("scene_count", 0) > 0 if visual else True,
                "needs_anonymization": anonymization.get("faces_detected", 0) > 0 if anonymization else False,
                "estimated_audience": "general",
            },
            "missing_analyses": missing,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "models_used": [],
            "cost_total_usd": 0.0,
        }

    def _estimate_cost(self, analysis: dict) -> float:
        """Estimation du coût total des analyses (approximatif)."""
        # Coûts estimés par étape (en USD)
        costs = {
            "meta_analysis": 0.001,   # ~1000 tokens
            "text_analysis": 0.005,   # ~5000 tokens (transcript long)
            "visual_analysis": 0.010, # ~10 frames vision
            "anonymization": 0.002,   # CPU/GPU time
            "speakers": 0.003,        # Pyannote GPU time
            "fusion": 0.003,          # ~2000 tokens
        }
        total = sum(costs.values())
        return round(total, 4)

    def get_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "meta_analysis": {
                    "type": "object",
                    "description": "Résultat de MetaAnalysisStep",
                },
                "text_analysis": {
                    "type": "object",
                    "description": "Résultat de TextAnalysisStep",
                },
                "visual_analysis": {
                    "type": "object",
                    "description": "Résultat de VisualAnalysisStep",
                },
                "anonymization": {
                    "type": "object",
                    "description": "Résultat de AnonymizationStep",
                },
                "speakers": {
                    "type": "object",
                    "description": "Résultat de SpeakerAnalysisStep",
                },
                "job_id": {
                    "type": "string",
                    "description": "ID du job",
                },
            },
            "required": ["job_id"],
        }