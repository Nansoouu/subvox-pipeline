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

YTDLP_TIMEOUT = 30  # secondes


class CheckUrlResponse(BaseModel):
    url: str
    status: str  # ok | not_found | needs_cookies | private | age_restricted | unsupported | timeout | error
    title: str | None = None
    description: str | None = None
    thumbnail: str | None = None
    source: str | None = None
    source_label: str | None = None  # "YouTube", "X (Twitter)", etc.
    channel: str | None = None
    upload_date: str | None = None  # YYYYMMDD
    duration_s: int | None = None
    resolution: str | None = None
    view_count: int | None = None
    suggestion: str = ""
    cookies_advice: str | None = None
    error: str | None = None


def _check(url: str, cookies: str | None = None) -> dict:
    """Appelle yt-dlp en dry-run et analyse la réponse.
    
    Phase 1 (2-5s) : titre, source, durée, résolution
    Phase 2 (+15s) : description, miniature, chaîne (si besoin)
    """
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
            data = {
                "status": "ok",
                "title": parts[0] if len(parts) > 0 else "",
                "source": parts[1] if len(parts) > 1 else "unknown",
                "duration_s": int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else None,
                "resolution": parts[3] if len(parts) > 3 else "",
            }
            # Phase 2 : rich metadata (timeout plus long)
            rich_cmd = [
                "yt-dlp",
                "--print", "%(description)s|%(thumbnail)s|%(channel)s|%(upload_date)s|%(view_count)s",
                "--no-download", "--no-warnings", url,
            ]
            if cookies and os.path.exists(cookies):
                rich_cmd.extend(["--cookies", cookies])
            try:
                rich = subprocess.run(
                    rich_cmd, capture_output=True, text=True, timeout=YTDLP_TIMEOUT,
                    env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                )
                if rich.returncode == 0 and rich.stdout.strip():
                    rp = rich.stdout.strip().split("|")
                    data["description"] = rp[0] if len(rp) > 0 and rp[0] != "NA" else None
                    data["thumbnail"] = rp[1] if len(rp) > 1 and rp[1] != "NA" else None
                    data["channel"] = rp[2] if len(rp) > 2 and rp[2] != "NA" else None
                    data["upload_date"] = rp[3] if len(rp) > 3 and rp[3] != "NA" and rp[3] != "None" else None
                    data["view_count"] = int(rp[4]) if len(rp) > 4 and rp[4].isdigit() else None
            except subprocess.TimeoutExpired:
                pass  # Rich metadata is optional
            return data

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


SOURCE_LABELS = {
    "youtube": "YouTube", "twitter": "X (Twitter)", "tiktok": "TikTok",
    "instagram": "Instagram", "facebook": "Facebook", "vimeo": "Vimeo",
    "dailymotion": "Dailymotion", "twitch": "Twitch", "reddit": "Reddit",
    "linkedin": "LinkedIn", "pinterest": "Pinterest",
}

COOKIES_ADVICE = (
    "Ce site nécessite une connexion. Pour utiliser tes cookies :\n"
    "1. Installe l'extension 'Get cookies.txt' (ou 'cookies.txt export') sur Chrome\n"
    "2. Connecte-toi au site dans ton navigateur\n"
    "3. Exporte les cookies avec l'extension → cookies.txt\n"
    "4. Place le fichier cookies.txt à la racine du projet\n\n"
    "⚠️ Les cookies sont très sensibles — ne les partage JAMAIS et ne les utilise qu'en local."
)


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
        description=(data.get("description", "")[:300] + "...") if data.get("description") and len(data["description"]) > 300 else data.get("description"),
        thumbnail=data.get("thumbnail"),
        source=data.get("source"),
        source_label=SOURCE_LABELS.get(data.get("source", ""), data.get("source", "Inconnu")),
        channel=data.get("channel"),
        upload_date=data.get("upload_date"),
        duration_s=data.get("duration_s"),
        resolution=data.get("resolution"),
        view_count=data.get("view_count"),
        suggestion=_suggestion(data["status"]),
        cookies_advice=COOKIES_ADVICE if data["status"] == "needs_cookies" else None,
        error=data.get("error"),
    )
