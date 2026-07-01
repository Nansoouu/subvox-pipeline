"""
supabase_storage.py — Stockage local (fallback si pas de Supabase).

En mode local, les fichiers sont sauvegardés dans storage/ à la racine du projet.
Quand Supabase sera configuré (VPS), upload_video utilisera le bucket Supabase.
"""

import logging
import shutil
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# Dossier de stockage local
STORAGE_DIR = Path(__file__).resolve().parent.parent.parent / "storage"
STORAGE_DIR.mkdir(parents=True, exist_ok=True)


async def upload_video(job_id: str, file_path: Path, filename: str = "") -> dict | None:
    """
    Sauvegarde une vidéo localement.
    Retourne {"storage_url": "file:///chemin/vers/le/fichier.mp4"}.
    Fallback vers Supabase si configuré (via subvox-confidential).
    """
    from core.config import settings

    # Si Supabase est configuré, déléguer au module confidentiel
    supabase_url = getattr(settings, "SUPABASE_URL", "") or ""
    if supabase_url:
        try:
            from core.supabase_storage_real import upload_video as _real_upload
            return await _real_upload(job_id, file_path, filename=filename)
        except (ImportError, Exception) as e:
            logger.warning(f"Supabase upload failed, falling back to local: {e}")

    # Mode local
    if not file_path or not Path(file_path).exists():
        logger.error(f"Fichier introuvable pour upload local: {file_path}")
        return None

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest_name = filename or f"{job_id}_{ts}.mp4"
    dest = STORAGE_DIR / dest_name

    try:
        shutil.copy2(str(file_path), str(dest))
        logger.info(f"Video stored locally: {dest} ({dest.stat().st_size // 1024} KB)")
        return {"storage_url": f"file://{dest}"}
    except Exception as e:
        logger.error(f"Local storage failed: {e}")
        return None


async def upload_text(*args, **kwargs) -> dict | None:
    """Stub — upload de texte non implémenté en local."""
    return None


# Stubs pour compatibilité
async def check_quota(*args, **kwargs):
    return True, ""


def record_usage(*args, **kwargs):
    pass


async def send_confirmation_email(*args, **kwargs):
    return True


class SubtitleConfig:
    """Stub — voir core.subtitle_config pour l'implémentation réelle."""
    defaults: dict = {}

    def __init__(self, *args, **kwargs):
        pass


def load_user_style_from_json(*args, **kwargs):
    return None
