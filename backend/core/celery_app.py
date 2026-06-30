"""
core/celery_app.py — Configuration Celery — Subvox Pipeline
"""

from celery import Celery

from core.config import settings
from core.logging_setup import get_logger

logger = get_logger(__name__)

celery_app = Celery(
    "SubvoxPipeline",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

# ── Import des tâches ──────────────────────────────────────────
import tasks.pipeline_task  # noqa: F401

# ── Queues ─────────────────────────────────────────────────────
QUEUE_CONFIG: dict[str, dict] = {
    "short": {"max_duration_s": 120, "concurrency": 4, "label": "< 2 min"},
    "medium": {"max_duration_s": 300, "concurrency": 2, "label": "2-5 min"},
    "long": {"max_duration_s": 900, "concurrency": 1, "label": "5-15 min"},
    "xlong": {"max_duration_s": float("inf"), "concurrency": 1, "label": "> 15 min"},
}


def get_queue_for_duration(duration_s: float) -> str:
    for queue_name, config in QUEUE_CONFIG.items():
        if duration_s <= config["max_duration_s"]:
            return queue_name
    return "xlong"


celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Europe/Paris",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_default_queue="video_processing",
    task_reject_on_worker_lost=True,
    task_acks_on_failure_or_timeout=True,
    result_expires=3600,
    worker_disable_rate_limits=True,
    task_routes={
        "tasks.pipeline_task.process_video_task": {
            "queue": "video_processing",
        },
    },
)
