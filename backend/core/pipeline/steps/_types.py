"""
Types partagés pour les étapes du pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class StepResult:
    """Conteneur standard pour le résultat d'une étape du pipeline."""

    success: bool = True
    data: dict[str, Any] = field(default_factory=dict)
    files: dict[str, str] = field(default_factory=dict)
    error: str = ""