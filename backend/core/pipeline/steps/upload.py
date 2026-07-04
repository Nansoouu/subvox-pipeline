"""
Étape 11 : Upload de la vidéo finale vers Supabase.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from core.logging_setup import get_logger
from core.config import settings
from core.pipeline.steps._helpers import _get_tmp
from core.pipeline.steps._types import StepResult

logger = get_logger(__name__)


async def step_upload(
    job_id: str,
    source_path: str = "",
    prefix: str = "translated_",
) -> StepResult:
    """
    Upload la vidéo finale vers Supabase Storage.
    """
    from core.supabase_storage import upload_video as _upload_video

    log_extra = {"job_id": job_id}
    tmp = _get_tmp(job_id)
    burned_path = Path(source_path) if source_path else tmp / "burned.mp4"

    if not burned_path.exists():
        raise RuntimeError("Fichier burned introuvable pour upload")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    upload_filename = f"{prefix}{ts}.mp4"
    logger.info(f"Upload -> {upload_filename}", extra=log_extra)

    upload_res = await _upload_video(str(job_id), burned_path, filename=upload_filename)
    if not upload_res:
        # Fallback: local storage (dev mode — no Supabase)
        logger.info("Supabase upload failed — saving locally", extra=log_extra)
        local_dir = Path(settings.LOCAL_STORAGE_DIR) if hasattr(settings, "LOCAL_STORAGE_DIR") else Path("/tmp/subvox-output")
        local_dir.mkdir(parents=True, exist_ok=True)
        local_path = local_dir / upload_filename
        import shutil
        shutil.copy2(burned_path, local_path)
        storage_key = f"file://{local_path}"
        logger.info(f"Saved locally: {storage_key}", extra=log_extra)
    else:
        storage_key = upload_res["storage_url"]

    file_size_mb = 0.0
    if burned_path.exists():
        file_size_mb = round(burned_path.stat().st_size / (1024 * 1024), 2)

    return StepResult(
        data={
            "storage_url": storage_key,
            "upload_filename": upload_filename,
            "file_size_mb": file_size_mb,
        },
    )