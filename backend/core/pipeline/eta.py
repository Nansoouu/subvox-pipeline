"""
pipeline/eta.py — Moteur d'estimation de temps restant — Subvox

ETAEngine calcule et recalibre l'ETA du pipeline de traduction vidéo.
Utilise les durées réelles des étapes déjà complétées pour affiner
les prédictions des étapes restantes.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from core.logging_setup import get_logger

logger = get_logger(__name__)


# ─── Poids de chaque étape dans l'estimation globale ──────────────────────────
# Somme = 1.0
STEP_WEIGHTS: dict[str, float] = {
    "downloading": 0.05,
    "transcribing": 0.20,
    "filtering": 0.02,
    "summary": 0.03,
    "translating": 0.30,
    "segments_save": 0.01,
    "ass_generation": 0.02,
    "watermark": 0.02,
    "burning": 0.30,
    "uploading": 0.05,
}

# Facteurs de base pour l'estimation initiale (pour une vidéo de 60s)
# Ces valeurs seront recalibrées au fur et à mesure
BASE_ESTIMATES: dict[str, float] = {
    "downloading": 15.0,  # 15s de download
    "transcribing": 60.0,  # 60s de transcription
    "filtering": 5.0,  # 5s de filtre
    "summary": 10.0,  # 10s de résumé LLM
    "translating": 90.0,  # 90s de traduction
    "segments_save": 3.0,  # 3s de sauvegarde
    "ass_generation": 5.0,  # 5s d'ASS
    "watermark": 3.0,  # 3s de watermark
    "burning": 90.0,  # 90s de burn (le plus long)
    "uploading": 10.0,  # 10s d'upload
}


class ETAEngine:
    """
    Moteur d'ETA qui recalibre dynamiquement les prédictions.

    Utilisation :
        eta = ETAEngine(video_duration_s=120.0)
        initial = eta.calculate_initial_eta()
        recalcule = eta.recalculate(step_timings, current_step, step_data)
        intra = eta.estimate_intra_step(current=5, total=20, step_name="translating", elapsed_in_step=30.0)
    """

    def __init__(self, video_duration_s: float = 0.0) -> None:
        self.video_duration_s = video_duration_s
        self._step_weights = dict(STEP_WEIGHTS)
        self._base_estimates = dict(BASE_ESTIMATES)
        # Cache des durées réelles des étapes déjà complétées (step_name -> duration_s)
        self._actual_durations: dict[str, float] = {}
        # Facteur de recalibrage global (1.0 = pas de recalibrage)
        self._calibration_factor: float = 1.0

    # ── Helpers ─────────────────────────────────────────────────────────────

    def _get_step_order(self, step_name: str) -> int:
        """Retourne l'ordre d'exécution d'une étape."""
        order = list(self._step_weights.keys())
        try:
            return order.index(step_name)
        except ValueError:
            return -1

    def _estimate_step_duration(self, step_name: str) -> float:
        """
        Estime la durée d'une étape en tenant compte de la durée vidéo
        et des durées réelles déjà mesurées.
        """
        base = self._base_estimates.get(step_name, 30.0)

        # Les étapes qui dépendent de la durée vidéo
        video_scaling = {
            "downloading": 0.1,  # 0.1s par seconde de vidéo
            "transcribing": 0.8,  # 0.8s par seconde (proche du temps réel)
            "filtering": 0.02,
            "translating": 1.2,  # 1.2s par seconde de vidéo
            "burning": 1.0,  # ~1x la durée vidéo
            "uploading": 0.05,
        }

        scale = video_scaling.get(step_name, 0.0)
        estimated = base + (self.video_duration_s * scale)

        # Si on a une durée réelle pour cette étape, l'utiliser
        if step_name in self._actual_durations:
            actual = self._actual_durations[step_name]
            # Moyenne pondérée : 30% base + 70% réel
            estimated = (0.3 * estimated) + (0.7 * actual)

        return max(estimated, 1.0)  # minimum 1s

    # ── API publique ────────────────────────────────────────────────────────

    def calculate_initial_eta(self) -> dict:
        """
        Calcule l'ETA initial basé sur la durée vidéo.
        Retourne un dict avec les clés :
            - remaining_seconds: float
            - total_estimated_seconds: float
            - steps: dict[str, float]  (estimation par étape)
        """
        total = 0.0
        steps_est: dict[str, float] = {}
        for step_name in self._step_weights:
            dur = self._estimate_step_duration(step_name)
            steps_est[step_name] = round(dur, 1)
            total += dur

        return {
            "remaining_seconds": round(total, 1),
            "total_estimated_seconds": round(total, 1),
            "steps": steps_est,
            "recalibrated": False,
        }

    def recalculate(
        self,
        step_timings: dict[str, Any],
        current_step: str,
        step_data: dict[str, Any] | None = None,
    ) -> dict:
        """
        Recalibre l'ETA après chaque étape terminée, basé sur les durées
        réelles des étapes déjà complétées.

        step_timings: dict de step_timings depuis la DB
        current_step: nom de l'étape en cours
        step_data: données optionnelles de l'étape (pour chunks, etc.)

        Retourne un dict ETA mis à jour.
        """
        # Extraire les durées réelles des étapes complétées
        for step_name, timing in step_timings.items():
            if isinstance(timing, dict):
                dur = timing.get("duration_s")
                if dur and dur > 0:
                    self._actual_durations[step_name] = dur

        # Calculer le facteur de recalibrage basé sur les étapes complétées
        completed_steps = [s for s in self._step_weights if s in self._actual_durations]
        if completed_steps:
            estimated_total = 0.0
            actual_total = 0.0
            for s in completed_steps:
                estimated_total += self._base_estimates.get(s, 30.0) + (
                    self.video_duration_s
                    * {
                        "downloading": 0.1,
                        "transcribing": 0.8,
                        "filtering": 0.02,
                        "translating": 1.2,
                        "burning": 1.0,
                        "uploading": 0.05,
                    }.get(s, 0.0)
                )
                actual_total += self._actual_durations[s]

            if estimated_total > 0:
                self._calibration_factor = actual_total / estimated_total
        else:
            self._calibration_factor = 1.0

        # Calculer l'ETA pour les étapes restantes
        remaining = 0.0
        remaining_steps: dict[str, float] = {}
        in_future = False
        for step_name in self._step_weights:
            if step_name == current_step:
                in_future = True
            if in_future:
                dur = self._estimate_step_duration(step_name) * self._calibration_factor
                remaining_steps[step_name] = round(dur, 1)
                remaining += dur

        # Ajuster pour l'étape en cours si on a des données step_data
        current_elapsed = 0.0
        current_estimated = remaining_steps.get(current_step, 30.0)
        if step_data and "current" in step_data and "total" in step_data:
            chunk_pct = step_data["current"] / max(step_data["total"], 1)
            current_elapsed = current_estimated * chunk_pct
            remaining = max(remaining - current_elapsed, 0.0)

        return {
            "remaining_seconds": round(remaining, 1),
            "total_estimated_seconds": round(
                sum(self._actual_durations.values()) + remaining, 1
            ),
            "steps": remaining_steps,
            "current_step": current_step,
            "calibration_factor": round(self._calibration_factor, 3),
            "recalibrated": len(completed_steps) > 0,
        }

    def estimate_intra_step(
        self,
        current: int,
        total: int,
        step_name: str,
        elapsed_in_step: float,
    ) -> dict:
        """
        Estime le temps restant pour l'étape en cours basé sur
        la progression intra-étape (chunks, frames, etc.).

        current: position actuelle (ex: chunk 5)
        total: total (ex: 20 chunks)
        step_name: nom de l'étape
        elapsed_in_step: temps écoulé depuis le début de l'étape (en secondes)

        Retourne un dict avec l'ETA intra-étape.
        """
        if total <= 0 or current <= 0:
            step_est = self._estimate_step_duration(step_name)
            return {
                "step_eta_seconds": round(step_est, 1),
                "step_elapsed": round(elapsed_in_step, 1),
                "step_progress_pct": 0,
            }

        progress_pct = min(100, int((current / total) * 100))
        if progress_pct > 0:
            estimated_total = elapsed_in_step / (progress_pct / 100.0)
            step_remaining = max(estimated_total - elapsed_in_step, 0.0)
        else:
            step_remaining = self._estimate_step_duration(step_name)

        return {
            "step_eta_seconds": round(step_remaining, 1),
            "step_elapsed": round(elapsed_in_step, 1),
            "step_progress_pct": progress_pct,
        }


def compute_video_category(duration_s: float) -> str:
    """
    Calcule la catégorie vidéo basée sur la durée.
    short: < 180s (3 min)
    medium: 180-900s (3-15 min)
    long: 900-3600s (15-60 min)
    very_long: > 3600s (60+ min)
    """
    if duration_s <= 0:
        return "short"
    if duration_s < 180:
        return "short"
    elif duration_s < 900:
        return "medium"
    elif duration_s < 3600:
        return "long"
    else:
        return "very_long"
