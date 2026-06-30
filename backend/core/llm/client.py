"""
core/llm/client.py — Client LLM pour les traitements locaux (fallback) — Subvox
"""

from core.logging_setup import get_logger

logger = get_logger(__name__)

# Ce module sert de point d'entrée pour les appels LLM.
# Le client principal est dans core/openrouter.py.
# Ce fichier est conservé pour compatibilité.

logger.debug("core/llm/client.py chargé (délègue à openrouter)")
