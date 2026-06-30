"""
prompts.py — Proxy de compatibilité.
Tous les prompts ont été déplacés dans backend/core/llm/prompts/.
Ce fichier réexporte tout depuis le nouveau package pour la rétrocompatibilité.
"""

from core.llm.prompts import *  # noqa: F401, F403