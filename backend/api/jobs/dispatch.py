"""api/jobs/dispatch.py — Internal dispatch endpoint.

Economy calls this instead of Celery send_task directly.
This avoids Redis binding issues between containers.
"""
import json
from uuid import UUID
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from core.logging_setup import get_logger
from tasks.pipeline_task import process_video_task
from core.db import direct_connect

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
    """Dispatch a job to the Celery worker."""
    try:
        result = process_video_task.delay(
            job_id=req.job_id,
            source_url=req.source_url,
            target_lang=req.target_lang,
            user_id=req.user_id,
        )
        logger.info(
            f"Job {req.job_id[:8]} dispatched (task {result.id[:8]})",
            extra={"job_id": req.job_id[:8], "lang": req.target_lang},
        )
        return {"status": "ok", "task_id": result.id}
    except Exception as e:
        logger.error(f"Dispatch failed for {req.job_id[:8]}: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


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
