"""supabase_storage.py — Stockage local uniquement.

Les fichiers sont sauvegardés dans pipeline/storage/ à la racine.
Retourne une URL file:// que le frontend sert via /jobs/{id}/download.
"""
from __future__ import annotations

import logging
import shutil
from datetime import datetime
from pathlib import Path

from core.config import settings

logger = logging.getLogger(__name__)

# Dossier de stockage local
STORAGE_DIR = Path(__file__).resolve().parent.parent.parent / "storage"
STORAGE_DIR.mkdir(parents=True, exist_ok=True)


async def upload_video(
    job_id: str, file_path: Path, filename: str = ""
) -> dict | None:
    """Copie une video dans le stockage local et retourne une URL file://.

    Returns:
        {"storage_url": "file:///chemin/vers/le/fichier.mp4"} ou None si echec.
    """
    if not file_path or not Path(file_path).exists():
        logger.error(f"Fichier introuvable pour upload local: {file_path}")
        return None

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest_name = filename or f"{job_id}_{ts}.mp4"
    dest = STORAGE_DIR / dest_name

    try:
        shutil.copy2(str(file_path), str(dest))
        logger.info(
            f"Video stored locally: {dest} ({dest.stat().st_size // 1024} KB)"
        )
        return {"storage_url": f"file://{dest}"}
    except Exception as e:
        logger.error(f"Local storage failed: {e}")
        return None


async def upload_text(*args, **kwargs) -> dict | None:
    """Stub — upload de texte non implemente en local."""
    return None


# ── Stubs pour compatibilite ──────────────────────────────────────────────────


async def check_quota(*args, **kwargs) -> tuple[bool, str]:
    return True, ""


def record_usage(*args, **kwargs) -> None:
    pass


async def send_confirmation_email(*args, **kwargs) -> bool:
    return True


class SubtitleConfig:
    """Stub — voir core.subtitle_config pour l'implementation reelle."""

    defaults: dict = {}

    def __init__(self, *args, **kwargs) -> None:
        pass


def load_user_style_from_json(*args, **kwargs):
    return None
