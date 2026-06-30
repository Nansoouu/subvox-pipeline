"""
prompts/__init__.py — Réexporte tous les prompts depuis les sous-fichiers.
"""

from core.llm.prompts._categories import CATEGORIES, CATEGORY_VOICES
from core.llm.prompts.summary import (
    SEGMENTED_SUMMARY_PROMPT,
    ORCHESTRATOR_PROMPT,
    SUMMARY_SYSTEM_PROMPT,
)
from core.llm.prompts.translation import (
    TRANSLATE_SRT_SYSTEM_PROMPT,
    TRANSLATE_SRT_USER_PROMPT,
    TRANSLATE_SUMMARY_SYSTEM_PROMPT,
)

__all__ = [
    "CATEGORIES",
    "CATEGORY_VOICES",
    "SEGMENTED_SUMMARY_PROMPT",
    "ORCHESTRATOR_PROMPT",
    "SUMMARY_SYSTEM_PROMPT",
    "TRANSLATE_SRT_SYSTEM_PROMPT",
    "TRANSLATE_SRT_USER_PROMPT",
    "TRANSLATE_SUMMARY_SYSTEM_PROMPT",
]