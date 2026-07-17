"""api/jobs/upload.py — Upload local video file, create job, auto-generate title."""
import uuid, os, shutil
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Request
from core.logging_setup import get_logger
from core.db import get_conn
from core.config import settings

logger = get_logger(__name__)
router = APIRouter()

UPLOAD_DIR = Path("/tmp/subvox-uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

VALID_LANGS = {"ar","de","en","es","fa","fr","he","hi","id","it","ja","ko","nl","pl","pt","ru","tr","vi","zh"}


@router.post("/upload")
async def upload_video(
    request: Request,
    file: UploadFile = File(...),
    mode: str = Form("translate"),
    target_lang: str = Form("fr"),
):
    if mode not in ("download", "translate"):
        raise HTTPException(400, "Mode invalide")
    if mode == "translate" and target_lang not in VALID_LANGS:
        raise HTTPException(400, f"Langue non supportée: {target_lang}")

    # Vérifier le fichier
    if not file.filename:
        raise HTTPException(400, "Fichier requis")
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in (".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"):
        raise HTTPException(400, f"Format non supporté: {ext}")

    job_id = str(uuid.uuid4())
    dest = UPLOAD_DIR / f"{job_id}{ext}"

    # Sauvegarder
    try:
        with open(dest, "wb") as f:
            shutil.copyfileobj(file.file, f)
    except Exception as e:
        logger.error("Upload échoué", extra={"error": str(e)})
        raise HTTPException(500, "Erreur lors de la sauvegarde du fichier")

    source_url = f"file://{dest}"
    user_id = ""

    # Créer le job en DB
    download_only = mode == "download"
    try:
        async with get_conn() as conn:
            await conn.execute(
                """INSERT INTO jobs (id, source_url, target_lang, status, mode, user_id, created_at)
                   VALUES ($1,$2,$3,'queued',$4,$5,now())""",
                job_id, source_url, target_lang if not download_only else None,
                mode, user_id,
            )
    except Exception as e:
        logger.error("DB insert échoué", extra={"error": str(e)})
        dest.unlink(missing_ok=True)
        raise HTTPException(500, "Erreur DB")

    # Lancer le pipeline Celery
    try:
        from tasks.pipeline_task import process_video_task
        process_video_task.delay(
            job_id=job_id,
            source_url=source_url,
            target_lang=target_lang,
            user_id=user_id,
            download_only=download_only,
            original_filename=file.filename,
        )
    except Exception as e:
        logger.warning("Celery trigger échoué", extra={"error": str(e)})
        # Le job est en DB, le heartbeat le reprendra

    logger.info("Upload réussi", extra={"job_id": job_id[:8], "filename": file.filename, "size": dest.stat().st_size})

    return {
        "job_id": job_id,
        "status": "queued",
        "source_url": source_url,
    }
