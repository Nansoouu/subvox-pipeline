"""api/jobs/dispatch.py — Internal dispatch endpoint."""
import json
import uuid
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from core.logging_setup import get_logger
from core.config import settings

logger = get_logger(__name__)
router = APIRouter()

import redis as _redis

_redis_client = _redis.Redis.from_url(settings.REDIS_URL)


class DispatchRequest(BaseModel):
    job_id: str
    source_url: str
    target_lang: str
    user_id: str = "system"


class RollbackRequest(BaseModel):
    job_id: str


@router.post("/dispatch", status_code=200)
async def dispatch_job(req: DispatchRequest):
    """Push a Celery task directly to the xlong Redis queue."""
    try:
        task_id = str(uuid.uuid4())
        task_msg = json.dumps({
            "id": task_id,
            "task": "tasks.pipeline_task.process_video_task",
            "args": [],
            "kwargs": {
                "job_id": req.job_id,
                "source_url": req.source_url,
                "target_lang": req.target_lang,
                "user_id": req.user_id,
            },
        })
        _redis_client.lpush("xlong", task_msg)
        logger.info(f"Job {req.job_id[:8]} dispatched (task {task_id[:8]})")
        return {"status": "ok", "task_id": task_id}
    except Exception as e:
        logger.error(f"Dispatch failed for {req.job_id[:8]}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/dispatch/batch", status_code=200)
async def dispatch_batch(reqs: list[DispatchRequest]):
    """Dispatch multiple jobs at once."""
    results = []
    for req in reqs:
        try:
            result = process_video_task.delay(
                job_id=req.job_id,
                source_url=req.source_url,
                target_lang=req.target_lang,
                user_id=req.user_id,
            )
            results.append({
                "job_id": req.job_id[:8],
                "status": "ok",
                "task_id": result.id,
            })
        except Exception as e:
            results.append({
                "job_id": req.job_id[:8],
                "status": "error",
                "error": str(e),
            })
    return results
