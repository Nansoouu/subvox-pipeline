"""
core/upload_helpers.py — Helpers d'upload fichier pour jobs — Subvox
"""

import os
import uuid
from pathlib import Path
from typing import Optional
from fastapi import UploadFile

from core.config import settings
from core.logging_setup import get_logger

logger = get_logger(__name__)

ACCEPTED_VIDEO_TYPES = [
    "video/mp4",
    "video/quicktime",
    "video/x-msvideo",
    "video/x-matroska",
    "video/webm",
    "video/3gpp",
    "video/mpeg",
]

MAX_FILE_SIZE = 1_000_000_000  # 1 GB


def _is_valid_video_file(file: UploadFile) -> tuple[bool, str]:
    """Valide le type MIME et la taille du fichier uploadé."""
    if file.content_type not in ACCEPTED_VIDEO_TYPES:
        return False, f"Type non supporté: {file.content_type}"
    try:
        file.file.seek(0, 2)
        size = file.file.tell()
        file.file.seek(0)
        if size > MAX_FILE_SIZE:
            return False, f"Taille max dépassée: {size} > {MAX_FILE_SIZE}"
        if size == 0:
            return False, "Fichier vide"
    except Exception as e:
        return False, f"Erreur validation: {e}"
    return True, ""


def _save_uploaded_file(file: UploadFile, job_id: str) -> str:
    """Sauvegarde le fichier uploadé sur le disque."""
    tmp = Path(settings.LOCAL_TEMP_DIR) / job_id
    tmp.mkdir(parents=True, exist_ok=True)
    ext = Path(file.filename or "video.mp4").suffix or ".mp4"
    output_path = tmp / f"source{ext}"
    content = file.file.read()
    output_path.write_bytes(content)
    logger.info(
        f"Fichier uploadé: {output_path} ({output_path.stat().st_size} octets)",
        extra={"job_id": job_id, "size": output_path.stat().st_size},
    )
    return str(output_path)


def _cleanup_uploaded_files(job_id: str):
    """Nettoie les fichiers uploadés d'un job."""
    import shutil

    tmp = Path(settings.LOCAL_TEMP_DIR) / job_id
    if tmp.exists():
        shutil.rmtree(tmp, ignore_errors=True)
        logger.debug(f"Cleanup upload: {tmp}")
