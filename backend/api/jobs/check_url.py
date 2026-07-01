"""
api/jobs/check_url.py — Endpoint de validation d'URL vidéo.
Vérifie si une URL est accessible et peut être traitée par yt-dlp.
"""

import os
import subprocess

from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel

from core.logging_setup import get_logger

logger = get_logger(__name__)
router = APIRouter()

YTDLP_TIMEOUT = 15  # secondes


class CheckUrlResponse(BaseModel):
    url: str
    status: str  # ok | not_found | needs_cookies | private | age_restricted | unsupported | timeout | error
    title: str | None = None
    source: str | None = None
    duration_s: int | None = None
    resolution: str | None = None
    suggestion: str = ""
    error: str | None = None


def _check(url: str, cookies: str | None = None) -> dict:
    """Appelle yt-dlp en dry-run et analyse la réponse."""
    cmd = [
        "yt-dlp",
        "--print", "%(title)s|%(extractor)s|%(duration)s|%(resolution)s",
        "--no-download", "--no-warnings",
        url,
    ]
    if cookies and os.path.exists(cookies):
        cmd.extend(["--cookies", cookies])

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=YTDLP_TIMEOUT,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
        if result.returncode == 0 and result.stdout.strip():
            parts = result.stdout.strip().split("|")
            return {
                "status": "ok",
                "title": parts[0] if len(parts) > 0 else "",
                "source": parts[1] if len(parts) > 1 else "unknown",
                "duration_s": int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else None,
                "resolution": parts[3] if len(parts) > 3 else "",
            }

        stderr = result.stderr.lower()
        hints = {
            "404": ("not_found", "Vidéo introuvable (404)"),
            "403": ("needs_cookies", "Accès refusé — cookies requis"),
            "private": ("private", "Vidéo privée"),
            "age": ("age_restricted", "Vidéo restreinte (âge)"),
            "unsupported": ("unsupported", "Site non supporté"),
            "timeout": ("timeout", "Timeout — site trop lent"),
        }
        for keyword, (status, msg) in hints.items():
            if keyword in stderr:
                return {"status": status, "error": msg}
        return {"status": "error", "error": stderr[:300] if stderr else "Erreur inconnue"}

    except subprocess.TimeoutExpired:
        return {"status": "timeout", "error": f"Timeout après {YTDLP_TIMEOUT}s"}
    except FileNotFoundError:
        return {"status": "error", "error": "yt-dlp non installé sur le serveur"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def _suggestion(status: str) -> str:
    return {
        "ok": "✅ Prêt à traduire",
        "not_found": "❌ Vérifie le lien — vidéo introuvable",
        "needs_cookies": "🍪 Cookies requis (connexion nécessaire)",
        "private": "🔒 Mets la vidéo en public",
        "age_restricted": "🔞 Connecte-toi avec un compte",
        "unsupported": "⚠️ Site pas encore supporté par yt-dlp",
        "timeout": "⏱️ Site trop lent ou bloqué dans ta région",
        "error": "⚠️ Erreur — contacte le support",
    }.get(status, "⚠️ Voir détail")


@router.get("/check-url", response_model=CheckUrlResponse)
async def check_url(url: str = Query(..., description="URL de la vidéo à valider")):
    """
    Vérifie si une URL vidéo peut être traitée par le pipeline.
    Appelle yt-dlp en dry-run — aucune donnée n'est téléchargée.
    """
    if not url.startswith(("http://", "https://")):
        raise HTTPException(400, "URL invalide — doit commencer par http:// ou https://")

    logger.info("URL check requested", extra={"url": url[:80]})
    data = _check(url)

    # Si cookies requis, réessayer avec cookies.txt
    if data["status"] == "needs_cookies":
        cookies_path = os.path.join(os.path.dirname(__file__), "..", "..", "cookies.txt")
        if os.path.exists(cookies_path):
            data = _check(url, cookies_path)

    return CheckUrlResponse(
        url=url,
        status=data["status"],
        title=data.get("title"),
        source=data.get("source"),
        duration_s=data.get("duration_s"),
        resolution=data.get("resolution"),
        suggestion=_suggestion(data["status"]),
        error=data.get("error"),
    )
