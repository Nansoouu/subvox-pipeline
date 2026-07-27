"""api/jobs/submit.py — Simplified job submission endpoint."""
import uuid
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from core.logging_setup import get_logger
from core.db import direct_connect
from tasks.pipeline_task import process_video_task

logger = get_logger(__name__)
router = APIRouter()


class SubmitRequest(BaseModel):
    source_url: str
    target_lang: str
    mode: str = "translate"
    visitor_token: str | None = None
    visibility: str = "public"


@router.post("/submit")
async def submit_job(req: SubmitRequest):
    job_id = str(uuid.uuid4())
    source_url = req.source_url.strip()

    try:
        conn = direct_connect()
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO jobs (id, source_url, target_lang, mode, status, visitor_token, visibility, created_at)
               VALUES (%s, %s, %s, %s, 'queued', %s, %s, NOW())""",
            (job_id, source_url, req.target_lang, req.mode, req.visitor_token or str(uuid.uuid4()), req.visibility),
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        logger.error(f"DB insert failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    try:
        result = process_video_task.delay(
            job_id=job_id,
            source_url=source_url,
            target_lang=req.target_lang,
            user_id=req.visitor_token or "anonymous",
        )
        logger.info(f"Job {job_id[:8]} {req.target_lang} dispatched ({result.id[:8]})")
    except Exception as e:
        logger.error(f"Dispatch failed but job created {job_id[:8]}: {e}")

    return {"job_id": job_id, "status": "queued", "mode": req.mode}
