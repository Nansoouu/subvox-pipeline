"""
core/voice_profiles.py — CRUD des profils vocaux utilisateur
"""

import logging
from uuid import UUID

from core.db import get_pool

logger = logging.getLogger(__name__)


async def create_voice_profile(
    user_id: UUID,
    voicebox_profile_id: str,
    name: str,
    source_audio_path: str | None = None,
    engine: str = "qwen3-tts",
    language: str | None = None,
) -> dict:
    """Crée un enregistrement de profil vocal dans la DB."""
    pool = await get_pool()
    row = await pool.fetchrow(
        """
        INSERT INTO voice_profiles (user_id, voicebox_profile_id, name, source_audio_path, engine, language)
        VALUES ($1, $2, $3, $4, $5, $6)
        RETURNING id, user_id, voicebox_profile_id, name, source_audio_path, engine, language, created_at
        """,
        user_id,
        voicebox_profile_id,
        name,
        source_audio_path,
        engine,
        language,
    )
    if not row:
        raise RuntimeError("Échec création voice profile")
    logger.info("Voice profile créé: id=%s, name=%s", row["id"], name)
    return dict(row)


async def get_voice_profiles(user_id: UUID) -> list[dict]:
    """Liste les profils vocaux d'un utilisateur."""
    pool = await get_pool()
    rows = await pool.fetch(
        """
        SELECT id, user_id, voicebox_profile_id, name, source_audio_path, engine, language, created_at
        FROM voice_profiles
        WHERE user_id = $1
        ORDER BY created_at DESC
        """,
        user_id,
    )
    return [dict(r) for r in rows]


async def get_voice_profile(profile_id: UUID, user_id: UUID) -> dict | None:
    """Récupère un profil vocal par son ID."""
    pool = await get_pool()
    row = await pool.fetchrow(
        """
        SELECT id, user_id, voicebox_profile_id, name, source_audio_path, engine, language, created_at
        FROM voice_profiles
        WHERE id = $1 AND user_id = $2
        """,
        profile_id,
        user_id,
    )
    return dict(row) if row else None


async def delete_voice_profile(profile_id: UUID, user_id: UUID) -> bool:
    """Supprime un profil vocal. Retourne True si supprimé."""
    pool = await get_pool()
    result = await pool.execute(
        "DELETE FROM voice_profiles WHERE id = $1 AND user_id = $2",
        profile_id,
        user_id,
    )
    deleted = result != "DELETE 0"
    if deleted:
        logger.info("Voice profile supprimé: id=%s", profile_id)
    return deleted
