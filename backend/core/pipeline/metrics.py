"""
pipeline/metrics.py — Télémétrie structurée du pipeline — Subvox

Dataclasses pour capturer les métriques à chaque étape :
    - VideoMetrics      : format, codec, dimensions, durée, frame_rate, file_size
    - StepMetrics       : success, duration_s, error (une par étape)
    - SubtitleMetrics   : nb_lines, font_size, ass_output_size
    - BurnMetrics       : mode, total_frames, duration_s, output_size, fps_avg
    - CostMetrics       : groq, llm_summary, llm_translation, total_eur
    - JobMetrics        : snapshot complet d'un job

MetricsCollector accumule les données et écrit dans la colonne job_metrics (JSONB).
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Optional

from core.config import settings
from core.logging_setup import get_logger
from core.pipeline.ffmpeg import (
    _get_video_dims,
    _get_video_duration,
    _get_video_frames,
)

logger = get_logger(__name__)


# ─── Dataclasses ─────────────────────────────────────────────────────────────


@dataclass
class VideoMetrics:
    """Métriques vidéo collectées après téléchargement."""

    format: str = ""
    codec: str = ""
    width: int = 0
    height: int = 0
    duration_s: float = 0.0
    frame_rate: float = 0.0
    file_size_mb: float = 0.0
    aspect_ratio: str = ""


@dataclass
class StepMetrics:
    """Métriques d'une étape du pipeline."""

    success: bool = True
    duration_s: float = 0.0
    error: str = ""


@dataclass
class SubtitleMetrics:
    """Métriques des sous-titres générés."""

    total_lines: int = 0
    font_size: int = 14
    ass_file_size_kb: float = 0.0
    mode: str = "ass"  # ass | srt


@dataclass
class BurnMetrics:
    """Métriques du burn (encodage final)."""

    mode: str = "ass"
    total_frames: int = 0
    duration_s: float = 0.0
    output_size_mb: float = 0.0
    fps_avg: float = 0.0


@dataclass
class CostMetrics:
    """Métriques de coût API (Groq + LLM)."""

    groq_eur: float = 0.0
    llm_summary_eur: float = 0.0
    llm_translation_eur: float = 0.0
    total_eur: float = 0.0


@dataclass
class JobMetrics:
    """Snapshot complet des métriques d'un job."""

    job_id: str = ""
    source_url: str = ""
    source_lang: str = ""
    target_lang: str = ""
    video: Optional[VideoMetrics] = None
    steps: dict[str, StepMetrics] = field(default_factory=dict)
    subtitles: Optional[SubtitleMetrics] = None
    burn: Optional[BurnMetrics] = None
    cost: Optional[CostMetrics] = None
    total_duration_s: float = 0.0
    pipeline_started_at: float = 0.0
    pipeline_ended_at: float = 0.0


# ─── Collecteur ──────────────────────────────────────────────────────────────


# Registry thread-safe : job_id -> MetricsCollector
_collectors: dict[str, "MetricsCollector"] = {}


def get_collector(job_id: str) -> "MetricsCollector":
    """Retourne ou crée un MetricsCollector pour un job."""
    if job_id not in _collectors:
        _collectors[job_id] = MetricsCollector(job_id)
    return _collectors[job_id]


class MetricsCollector:
    """Accumule les métriques d'un job et les finalise dans la DB."""

    def __init__(self, job_id: str) -> None:
        self.job_id = job_id
        self._job_metrics = JobMetrics(
            job_id=job_id,
            pipeline_started_at=time.time(),
        )
        self._finalized = False

    # ── Enregistrement d'étape ────────────────────────────────────────────

    def record_step(
        self,
        step_name: str,
        success: bool = True,
        duration_s: float = 0.0,
        error: str = "",
    ) -> None:
        """Enregistre les métriques d'une étape."""
        self._job_metrics.steps[step_name] = StepMetrics(
            success=success,
            duration_s=duration_s,
            error=error,
        )
        logger.debug(
            "Step metrics recorded",
            extra={
                "job_id": self.job_id[:8],
                "step": step_name,
                "success": success,
                "duration_s": round(duration_s, 2),
            },
        )

    # ── Métriques vidéo ──────────────────────────────────────────────────

    def set_video_metrics(self, video_path: str | Path) -> None:
        """Collecte les métriques vidéo via FFprobe/stat."""
        vp = Path(video_path)
        if not vp.exists():
            logger.warning(
                "Video file not found for metrics",
                extra={"job_id": self.job_id[:8], "path": str(vp)},
            )
            return

        try:
            file_size_mb = vp.stat().st_size / (1024 * 1024)
            duration_s = _get_video_duration(vp) or 0.0
            width, height = _get_video_dims(vp) or (0, 0)
            total_frames = _get_video_frames(vp) or 0
            frame_rate = round(total_frames / duration_s, 2) if duration_s > 0 else 0.0

            # Format et codec via extension + ffprobe simple
            fmt = vp.suffix.lstrip(".").lower() or "mp4"
            codec = self._probe_codec(vp)

            aspect = f"{width}:{height}" if width and height else ""

            self._job_metrics.video = VideoMetrics(
                format=fmt,
                codec=codec,
                width=width,
                height=height,
                duration_s=round(duration_s, 2),
                frame_rate=frame_rate,
                file_size_mb=round(file_size_mb, 2),
                aspect_ratio=aspect,
            )
            logger.debug(
                "Video metrics collected",
                extra={
                    "job_id": self.job_id[:8],
                    "format": fmt,
                    "size": f"{width}x{height}",
                    "duration_s": f"{duration_s:.1f}s",
                    "file_size_mb": f"{file_size_mb:.1f}MB",
                },
            )
        except Exception as exc:
            logger.warning(
                "Failed to collect video metrics",
                extra={"job_id": self.job_id[:8], "error": str(exc)},
            )

    @staticmethod
    def _probe_codec(video: Path) -> str:
        """Probe le codec vidéo via ffprobe."""
        import subprocess

        ffprobe = os.environ.get("FFPROBE_PATH", "ffprobe")
        try:
            r = subprocess.run(
                [
                    ffprobe,
                    "-v",
                    "error",
                    "-select_streams",
                    "v:0",
                    "-show_entries",
                    "stream=codec_name",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    str(video),
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            return r.stdout.strip()[:32] if r.returncode == 0 else "unknown"
        except Exception:
            return "unknown"

    # ── Métriques sous-titres ────────────────────────────────────────────

    def set_subtitle_metrics(
        self,
        total_lines: int = 0,
        font_size: int = 14,
        ass_path: str | Path = "",
        mode: str = "ass",
    ) -> None:
        """Collecte les métriques des sous-titres."""
        ass_size_kb = 0.0
        if ass_path:
            ap = Path(ass_path)
            if ap.exists():
                ass_size_kb = ap.stat().st_size / 1024.0

        self._job_metrics.subtitles = SubtitleMetrics(
            total_lines=total_lines,
            font_size=font_size,
            ass_file_size_kb=round(ass_size_kb, 2),
            mode=mode,
        )

    # ── Métriques burn ───────────────────────────────────────────────────

    def set_burn_metrics(
        self,
        mode: str = "ass",
        total_frames: int = 0,
        duration_s: float = 0.0,
        output_size_mb: float = 0.0,
        fps_avg: float = 0.0,
    ) -> None:
        """Collecte les métriques du burn."""
        self._job_metrics.burn = BurnMetrics(
            mode=mode,
            total_frames=total_frames,
            duration_s=round(duration_s, 2),
            output_size_mb=round(output_size_mb, 2),
            fps_avg=round(fps_avg, 2),
        )

    # ── Métriques coût ───────────────────────────────────────────────────

    def set_cost_metrics(
        self,
        groq_eur: float = 0.0,
        llm_summary_eur: float = 0.0,
        llm_translation_eur: float = 0.0,
    ) -> None:
        """Ajoute des coûts aux métriques (cumulatif)."""
        cost = self._job_metrics.cost or CostMetrics()
        cost.groq_eur = round(cost.groq_eur + groq_eur, 6)
        cost.llm_summary_eur = round(cost.llm_summary_eur + llm_summary_eur, 6)
        cost.llm_translation_eur = round(
            cost.llm_translation_eur + llm_translation_eur, 6
        )
        cost.total_eur = round(
            cost.groq_eur + cost.llm_summary_eur + cost.llm_translation_eur, 6
        )
        self._job_metrics.cost = cost

    # ── Métadonnées job ──────────────────────────────────────────────────

    def set_meta(
        self,
        source_url: str = "",
        source_lang: str = "",
        target_lang: str = "",
    ) -> None:
        """Définit les métadonnées du job."""
        if source_url:
            self._job_metrics.source_url = source_url
        if source_lang:
            self._job_metrics.source_lang = source_lang
        if target_lang:
            self._job_metrics.target_lang = target_lang

    # ── Finalisation ─────────────────────────────────────────────────────

    def finalize(self) -> dict[str, Any]:
        """Finalise les métriques et écrit dans la DB (colonne job_metrics)."""
        if self._finalized:
            return self.to_dict()

        self._job_metrics.pipeline_ended_at = time.time()
        self._job_metrics.total_duration_s = round(
            self._job_metrics.pipeline_ended_at - self._job_metrics.pipeline_started_at,
            2,
        )

        # Recalculer le total
        if self._job_metrics.cost:
            c = self._job_metrics.cost
            c.total_eur = round(
                c.groq_eur + c.llm_summary_eur + c.llm_translation_eur, 6
            )

        data = self.to_dict()
        self._write_to_db(data)
        self._finalized = True

        # Nettoyer le registry
        _collectors.pop(self.job_id, None)

        logger.info(
            "Job metrics finalized",
            extra={
                "job_id": self.job_id[:8],
                "total_duration_s": self._job_metrics.total_duration_s,
                "steps": len(self._job_metrics.steps),
            },
        )
        return data

    def to_dict(self) -> dict[str, Any]:
        """Exporte les métriques en dict JSON-serializable."""
        return _json_serialize(asdict(self._job_metrics))

    def _write_to_db(self, data: dict[str, Any]) -> None:
        """Écrit les métriques dans la colonne job_metrics de la table jobs."""
        import uuid

        from core.db import direct_connect as _direct

        try:

            async def _write():
                async with _direct() as conn:
                    await conn.execute(
                        "UPDATE jobs SET job_metrics=$1::jsonb, updated_at=now() WHERE id=$2",
                        json.dumps(data),
                        uuid.UUID(self.job_id),
                    )

            import asyncio

            try:
                loop = asyncio.get_running_loop()
                if loop.is_running():
                    asyncio.ensure_future(_write())
                else:
                    asyncio.run(_write())
            except RuntimeError:
                asyncio.run(_write())
        except Exception as exc:
            logger.error(
                "Failed to write job metrics to DB",
                extra={"job_id": self.job_id[:8], "error": str(exc)},
            )


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _json_serialize(obj: Any) -> Any:
    """Convertit récursivement en types JSON-safe."""
    if isinstance(obj, dict):
        return {k: _json_serialize(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_json_serialize(v) for v in obj]
    elif isinstance(obj, float):
        # Éviter NaN / Infinity
        import math

        if math.isnan(obj) or math.isinf(obj):
            return None
        return round(obj, 6)
    elif obj is None or isinstance(obj, (str, int, bool)):
        return obj
    return str(obj)
