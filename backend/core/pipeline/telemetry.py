"""
pipeline/telemetry.py — Télémétrie enrichie du pipeline — Subvox

TelemetryWriter : écrit les données de progression, timings, ETA, etc.
dans Redis (en temps réel) et DB (colonnes JSONB) à chaque étape.

Utilisé par runner.py et les steps individuelles (step_translate notamment).
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from core.logging_setup import get_logger

logger = get_logger(__name__)


# ─── Helpers Redis ─────────────────────────────────────────────────────────────


def _get_redis():
    """Retourne un client Redis synchrone."""
    import redis as _redis
    from core.config import settings

    return _redis.from_url(settings.REDIS_URL, decode_responses=True)


async def set_step_progress(job_id: str, step_progress: dict) -> bool:
    """
    Écrit la progression intra-étape dans Redis.
    step_progress = {"step_name": "...", "current": 5, "total": 20, "label": "Chunk 5/20"}
    TTL: 3600s (1h — le temps max d'un pipeline)
    """
    try:
        r = _get_redis()
        key = f"job:{job_id}:step_progress"
        r.setex(key, 3600, json.dumps(step_progress))
        return True
    except Exception as e:
        logger.warning(
            "set_step_progress Redis error",
            extra={"job_id": job_id[:8], "error": str(e)},
        )
        return False


async def get_step_progress(job_id: str) -> dict | None:
    """Lit la progression intra-étape depuis Redis."""
    try:
        r = _get_redis()
        key = f"job:{job_id}:step_progress"
        val = r.get(key)
        if val:
            return json.loads(val)
        return None
    except Exception as e:
        logger.warning(
            "get_step_progress Redis error",
            extra={"job_id": job_id[:8], "error": str(e)},
        )
        return None


async def set_eta(job_id: str, eta_dict: dict) -> bool:
    """
    Écrit l'ETA calculé dans Redis.
    eta_dict = {
        "remaining_seconds": 120.0,
        "total_estimated_seconds": 600.0,
        "current_step": "translating",
        "step_elapsed": 45.0,
        "step_eta_seconds": 90.0,
        "recalibrated": True,
        "updated_at": "2026-05-01T12:00:00Z"
    }
    TTL: 120s (rafraîchi régulièrement)
    """
    try:
        r = _get_redis()
        key = f"job:{job_id}:eta"
        r.setex(key, 120, json.dumps(eta_dict))
        return True
    except Exception as e:
        logger.warning(
            "set_eta Redis error",
            extra={"job_id": job_id[:8], "error": str(e)},
        )
        return False


async def get_eta(job_id: str) -> dict | None:
    """Lit l'ETA depuis Redis."""
    try:
        r = _get_redis()
        key = f"job:{job_id}:eta"
        val = r.get(key)
        if val:
            return json.loads(val)
        return None
    except Exception as e:
        logger.warning(
            "get_eta Redis error",
            extra={"job_id": job_id[:8], "error": str(e)},
        )
        return None


# ─── TelemetryWriter ───────────────────────────────────────────────────────────


class TelemetryWriter:
    """
    Writer de télémétrie qui écrit dans la DB (colonnes JSONB) et Redis.
    Utilisé par runner.py à chaque étape du pipeline.

    Toutes les méthodes sont async et ignorent les erreurs (non-bloquant).
    """

    def __init__(self, job_id: str) -> None:
        self.job_id = job_id
        self._log_extra = {"job_id": job_id[:8]}

    # ── Redis helpers (progression en temps réel) ──────────────────────────

    async def update_step_progress(
        self,
        step_name: str,
        current: int,
        total: int,
        label: str = "",
    ) -> None:
        """
        Écrit la progression intra-étape dans Redis.
        Exemple : update_step_progress("translating", current=3, total=10, label="Chunk 3/10")
        """
        data = {
            "step_name": step_name,
            "current": current,
            "total": total,
            "label": label or f"{step_name} {current}/{total}",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        await set_step_progress(self.job_id, data)

    async def update_eta(self, eta_dict: dict) -> None:
        """Écrit l'ETA dans Redis."""
        eta_dict["updated_at"] = datetime.now(timezone.utc).isoformat()
        await set_eta(self.job_id, eta_dict)

    # ── DB helpers (données persistantes) ──────────────────────────────────

    async def _update_jsonb(self, column: str, value: Any) -> None:
        """UPDATE une colonne JSONB sur la table jobs."""
        from core.db import direct_connect as _direct

        try:
            async with _direct() as conn:
                await conn.execute(
                    f"UPDATE jobs SET {column}=$1::jsonb, updated_at=now() WHERE id=$2",
                    json.dumps(value),
                    uuid.UUID(self.job_id),
                )
        except Exception as e:
            logger.warning(
                f"TelemetryWriter _update_jsonb echoue: {column}",
                extra={"error": str(e), **self._log_extra},
            )

    async def update_step_timing(
        self,
        step_name: str,
        status: str = "completed",
        started_at: str | None = None,
        ended_at: str | None = None,
        duration_s: float | None = None,
    ) -> None:
        """
        Met à jour step_timings JSONB avec le timing d'une étape.
        Structure: {"step_name": {"status": "...", "started_at": "...", "ended_at": "...", "duration_s": 12.5}}
        """
        from core.db import direct_connect as _direct

        try:
            async with _direct() as conn:
                row = await conn.fetchrow(
                    "SELECT step_timings FROM jobs WHERE id=$1",
                    uuid.UUID(self.job_id),
                )
                timings: dict = row["step_timings"] or {} if row else {}
                if isinstance(timings, str):
                    timings = json.loads(timings)

                entry = timings.get(step_name, {})
                entry["status"] = status
                if started_at:
                    entry["started_at"] = started_at
                if ended_at:
                    entry["ended_at"] = ended_at
                if duration_s is not None:
                    entry["duration_s"] = round(duration_s, 2)
                # Màj updated_at dans l'entrée
                entry["updated_at"] = datetime.now(timezone.utc).isoformat()
                timings[step_name] = entry

                await conn.execute(
                    "UPDATE jobs SET step_timings=$1::jsonb, updated_at=now() WHERE id=$2",
                    json.dumps(timings),
                    uuid.UUID(self.job_id),
                )
        except Exception as e:
            logger.warning(
                "TelemetryWriter update_step_timing echoue",
                extra={"error": str(e), "step": step_name, **self._log_extra},
            )

    async def update_step_data(
        self,
        step_name: str,
        data_dict: dict[str, Any],
    ) -> None:
        """
        Met à jour step_data JSONB avec les données produites par une étape.
        Fusionne avec l'existant.
        Structure: {"step_name": {"key": "value", ...}}
        """
        from core.db import direct_connect as _direct

        try:
            async with _direct() as conn:
                row = await conn.fetchrow(
                    "SELECT step_data FROM jobs WHERE id=$1",
                    uuid.UUID(self.job_id),
                )
                existing: dict = row["step_data"] or {} if row else {}
                if isinstance(existing, str):
                    existing = json.loads(existing)

                existing[step_name] = data_dict

                await conn.execute(
                    "UPDATE jobs SET step_data=$1::jsonb, updated_at=now() WHERE id=$2",
                    json.dumps(existing),
                    uuid.UUID(self.job_id),
                )
        except Exception as e:
            logger.warning(
                "TelemetryWriter update_step_data echoue",
                extra={"error": str(e), "step": step_name, **self._log_extra},
            )

    async def update_source_info(self, info_dict: dict) -> None:
        """Écrit dans source_info JSONB."""
        await self._update_jsonb("source_info", info_dict)

    async def update_subtitle_info(self, info_dict: dict) -> None:
        """Écrit dans subtitle_info JSONB."""
        await self._update_jsonb("subtitle_info", info_dict)

    async def update_cost_breakdown(self, category: str, cost_dict: dict) -> None:
        """
        Ajoute un coût dans cost_breakdown JSONB.
        Fusionne avec l'existant pour le category donné.
        """
        from core.db import direct_connect as _direct

        try:
            async with _direct() as conn:
                row = await conn.fetchrow(
                    "SELECT cost_breakdown FROM jobs WHERE id=$1",
                    uuid.UUID(self.job_id),
                )
                existing: dict = row["cost_breakdown"] or {} if row else {}
                if isinstance(existing, str):
                    existing = json.loads(existing)

                existing[category] = cost_dict

                await conn.execute(
                    "UPDATE jobs SET cost_breakdown=$1::jsonb, updated_at=now() WHERE id=$2",
                    json.dumps(existing),
                    uuid.UUID(self.job_id),
                )
        except Exception as e:
            logger.warning(
                "TelemetryWriter update_cost_breakdown echoue",
                extra={"error": str(e), "category": category, **self._log_extra},
            )

    async def append_processing_log(
        self,
        event: str,
        step: str,
        message: str,
        extra: dict | None = None,
    ) -> None:
        """
        Ajoute une entrée dans processing_log JSONB array.
        Structure: [{"event": "...", "step": "...", "message": "...", "timestamp": "...", ...}]
        """
        from core.db import direct_connect as _direct

        entry = {
            "event": event,
            "step": step,
            "message": message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if extra:
            entry.update(extra)

        try:
            async with _direct() as conn:
                row = await conn.fetchrow(
                    "SELECT processing_log FROM jobs WHERE id=$1",
                    uuid.UUID(self.job_id),
                )
                log: list = row["processing_log"] or [] if row else []
                if isinstance(log, str):
                    log = json.loads(log)
                log.append(entry)

                await conn.execute(
                    "UPDATE jobs SET processing_log=$1::jsonb, updated_at=now() WHERE id=$2",
                    json.dumps(log),
                    uuid.UUID(self.job_id),
                )
        except Exception as e:
            logger.warning(
                "TelemetryWriter append_processing_log echoue",
                extra={"error": str(e), "event": event, **self._log_extra},
            )

    async def update_video_category(self, category: str) -> None:
        """Met à jour la colonne video_category VARCHAR."""
        from core.db import direct_connect as _direct

        try:
            async with _direct() as conn:
                await conn.execute(
                    "UPDATE jobs SET video_category=$1, updated_at=now() WHERE id=$2",
                    category,
                    uuid.UUID(self.job_id),
                )
        except Exception as e:
            logger.warning(
                "TelemetryWriter update_video_category echoue",
                extra={"error": str(e), **self._log_extra},
            )
