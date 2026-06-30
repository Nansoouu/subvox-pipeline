"""
core/tts_client.py — Client HTTP async pour Voicebox (sidecar TTS)
"""

import logging
from typing import Optional

import httpx

from core.config import settings

logger = logging.getLogger(__name__)

# Timeouts en secondes
CLONE_TIMEOUT = 60
GENERATE_TIMEOUT = 120
DEFAULT_TIMEOUT = 30


class TTSClient:
    """Client HTTP pour l'API Voicebox.

    Documentation Voicebox REST :
      POST /profiles  → upload audio, créer un profil vocal
      GET  /profiles  → lister les profils
      GET  /profiles/{id} → détail d'un profil
      POST /generate  → TTS avec un profil (voice cloning)
    """

    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = (base_url or settings.VOICEBOX_API_URL).rstrip("/")

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict | None = None,
        files: dict | None = None,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> dict | bytes:
        """Effectue une requête HTTP vers Voicebox."""
        url = f"{self.base_url}{path}"
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout)) as client:
            if method == "GET":
                resp = await client.get(url)
            elif method == "POST":
                if files:
                    resp = await client.post(url, files=files)
                else:
                    resp = await client.post(url, json=json_body or {})
            elif method == "DELETE":
                resp = await client.delete(url)
            else:
                raise ValueError(f"Méthode HTTP non supportée : {method}")

            resp.raise_for_status()

            # Si la réponse est du binaire (audio), retourner bytes
            content_type = resp.headers.get("content-type", "")
            if "audio" in content_type or "application/octet-stream" in content_type:
                return resp.content

            return resp.json()

    # ── Profils vocaux ────────────────────────────────────────────────────────

    async def clone_voice(self, audio_bytes: bytes, name: str) -> dict:
        """Crée un profil vocal à partir d'un échantillon audio.

        Args:
            audio_bytes: Fichier audio (WAV/MP3) de 5-10 secondes.
            name: Nom du profil.

        Returns:
            dict contenant l'id du profil Voicebox (ex: {"id": "..."}).
        """
        logger.info("Clonage vocal Voicebox : name=%s, size=%d", name, len(audio_bytes))
        result = await self._request(
            "POST",
            "/profiles",
            files={
                "audio": ("sample.wav", audio_bytes, "audio/wav"),
                "name": (None, name),
            },
            timeout=CLONE_TIMEOUT,
        )
        if isinstance(result, dict):
            logger.info("Profil vocal créé : %s", result.get("id", "?"))
        return result  # type: ignore[return-value]

    async def list_profiles(self) -> list[dict]:
        """Liste tous les profils vocaux disponibles."""
        result = await self._request("GET", "/profiles")
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            return result.get("profiles", result.get("data", []))
        return []

    async def get_profile(self, profile_id: str) -> dict:
        """Récupère les détails d'un profil vocal."""
        result = await self._request("GET", f"/profiles/{profile_id}")
        return result  # type: ignore[return-value]

    async def delete_profile(self, profile_id: str) -> dict:
        """Supprime un profil vocal."""
        result = await self._request("DELETE", f"/profiles/{profile_id}")
        return result  # type: ignore[return-value]

    # ── Génération TTS ────────────────────────────────────────────────────────

    async def generate_dub(
        self,
        text: str,
        profile_id: str,
        language: str = "fr",
        engine: str = "qwen3-tts",
    ) -> bytes:
        """Génère un audio parlé en voice cloning.

        Args:
            text: Texte à vocaliser.
            profile_id: ID du profil vocal Voicebox.
            language: Langue cible (code ISO 639-1).
            engine: Moteur TTS (qwen3-tts, xtts, coqui, etc.).

        Returns:
            bytes: Fichier audio WAV.
        """
        logger.info(
            "Génération TTS Voicebox : text_len=%d, profile=%s, lang=%s, engine=%s",
            len(text),
            profile_id,
            language,
            engine,
        )
        result = await self._request(
            "POST",
            "/generate",
            json_body={
                "text": text,
                "profile_id": profile_id,
                "language": language,
                "engine": engine,
            },
            timeout=GENERATE_TIMEOUT,
        )
        if isinstance(result, bytes):
            return result
        msg = f"Réponse inattendue de Voicebox (generate) : {type(result).__name__}"
        raise RuntimeError(msg)

    async def health(self) -> bool:
        """Vérifie que Voicebox est joignable."""
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(5)) as client:
                resp = await client.get(f"{self.base_url}/health")
                return resp.status_code < 500
        except Exception:
            return False


# Singleton pratique
tts_client = TTSClient()
