"""
pipeline/analysis_base.py — Classe de base abstraite pour les étapes d'analyse — Subvox

Chaque étape d'analyse (meta, text, visual, fusion) hérite de AnalysisStep
et expose une interface standardisée pour être appelable aussi bien depuis le
pipeline Celery que depuis un futur MCP server.

Design :
- analyze() : méthode asynchrone principale, retourne un dict structuré
- get_schema() : retourne le JSON Schema pour validation des inputs
- step_name : nom lisible de l'étape (auto-détecté depuis le nom de classe)
- validate_input() : validation des données d'entrée avant analyse
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod


class AnalysisStep(ABC):
    """
    Classe de base pour toutes les étapes d'analyse vidéo.

    Usage :
        class MetaAnalysisStep(AnalysisStep):
            async def analyze(self, input_data: dict) -> dict:
                ...
    """

    @abstractmethod
    async def analyze(self, input_data: dict) -> dict:
        """
        Analyse asynchrone. Retourne un dict structuré avec les résultats.

        Le format de retour dépend de l'étape et DOIT être compatible JSON.
        En cas d'erreur, retourner {"error": "message description"}.
        """
        ...

    @abstractmethod
    def get_schema(self) -> dict:
        """
        Retourne le JSON Schema pour l'input de cette étape.

        Utilisé pour :
        - Valider les inputs dans le pipeline
        - Générer la spec MCP tool automatiquement
        - Documenter l'API dans /docs

        Exemple :
        {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "description": {"type": "string"},
                "duration_s": {"type": "number"},
            },
            "required": ["title", "duration_s"],
        }
        """
        ...

    @property
    def step_name(self) -> str:
        """Nom lisible de l'étape, auto-détecté depuis le nom de classe."""
        name = self.__class__.__name__
        # CamelCase → snake_case, puis retire "step" suffix
        result = ""
        for char in name:
            if char.isupper() and result:
                result += "_"
            result += char.lower()
        return result.replace("step_", "")

    async def validate_input(self, input_data: dict) -> list[str]:
        """
        Valide les données d'entrée contre le schéma défini par get_schema().

        Retourne une liste d'erreurs de validation.
        Liste vide = input valide.
        """
        errors: list[str] = []
        schema = self.get_schema()
        required = schema.get("required", [])

        for field in required:
            if field not in input_data or input_data[field] is None:
                errors.append(f"Champ requis manquant : '{field}'")

        properties = schema.get("properties", {})
        for field, value in input_data.items():
            prop = properties.get(field)
            if prop is None:
                continue
            expected_type = prop.get("type")
            if expected_type and value is not None:
                type_map = {
                    "string": str,
                    "number": (int, float),
                    "boolean": bool,
                    "array": list,
                    "object": dict,
                }
                py_type = type_map.get(expected_type)
                if py_type and not isinstance(value, py_type):
                    errors.append(
                        f"Type invalide pour '{field}' : attendu {expected_type}, "
                        f"reçu {type(value).__name__}"
                    )

        return errors

    def to_json(self) -> str:
        """Retourne le step sous forme JSON (pour logs, caching, MCP)."""
        return json.dumps(
            {
                "step_name": self.step_name,
                "schema": self.get_schema(),
            },
            indent=2,
            ensure_ascii=False,
        )