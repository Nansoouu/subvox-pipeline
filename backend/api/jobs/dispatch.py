"""api/jobs/dispatch.py — Internal dispatch endpoint."""
import json
import uuid
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from core.logging_setup import get_logger
from core.celery_app import celery_app

logger = get_logger(__name__)
router = APIRouter()


class DispatchRequest(BaseModel):
    job_id: str
    source_url: str
    target_lang: str
    user_id: str = "system"


class RollbackRequest(BaseModel):
    job_id: str


@router.post("/dispatch", status_code=200)
async def dispatch_job(req: DispatchRequest):
    """Dispatch a job to the Celery worker via send_task."""
    try:
        result = celery_app.send_task(
            "tasks.pipeline_task.process_video_task",
            args=[],
            kwargs={
                "job_id": req.job_id,
                "source_url": req.source_url,
                "target_lang": req.target_lang,
                "user_id": req.user_id,
            },
            queue="xlong",
        )
        logger.info(f"Job {req.job_id[:8]} dispatched (task {result.id[:8]})")
        return {"status": "ok", "task_id": result.id}
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
