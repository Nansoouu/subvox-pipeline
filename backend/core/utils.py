"""
core/utils.py - Utilitaires généraux pour x-translator-mvp
Inclut le formatage de temps pour logs et API.
"""


def format_duration_human(seconds: float) -> str:
    """
    Convertit des secondes en format lisible humain.

    Exemples :
    7054 → "1h57m"
    3527.3 → "59m"
    125 → "2m5s"
    60 → "1m"
    30 → "30s"
    3600 → "1h"
    3661 → "1h1m1s"
    """
    if seconds < 60:
        return f"{int(seconds)}s"

    minutes = seconds / 60
    if minutes < 60:
        remaining_seconds = seconds % 60
        if remaining_seconds < 1:
            return f"{int(minutes)}m"
        else:
            return f"{int(minutes)}m{int(remaining_seconds)}s"

    hours = minutes / 60
    if hours < 24:
        remaining_minutes = int(minutes % 60)
        if remaining_minutes == 0:
            return f"{int(hours)}h"
        else:
            return f"{int(hours)}h{remaining_minutes}m"

    days = hours / 24
    remaining_hours = int(hours % 24)
    if remaining_hours == 0:
        return f"{int(days)}j"
    else:
        return f"{int(days)}j{remaining_hours}h"


def format_duration_detailed(seconds: float) -> str:
    """
    Format détaillé pour logs et affichage API.

    Exemple :
    7054.0 → "1 heure 57 minutes 4 secondes"
    3527.3 → "58 minutes 47 secondes"
    125 → "2 minutes 5 secondes"
    """
    if seconds < 60:
        return f"{int(seconds)} seconde{'s' if seconds > 1 else ''}"

    minutes = seconds / 60
    if minutes < 60:
        whole_minutes = int(minutes)
        remaining_seconds = int(seconds % 60)
        if remaining_seconds == 0:
            return f"{whole_minutes} minute{'s' if whole_minutes > 1 else ''}"
        else:
            return f"{whole_minutes} minute{'s' if whole_minutes > 1 else ''} {remaining_seconds} seconde{'s' if remaining_seconds > 1 else ''}"

    hours = minutes / 60
    if hours < 24:
        whole_hours = int(hours)
        remaining_minutes = int(minutes % 60)
        if remaining_minutes == 0:
            return f"{whole_hours} heure{'s' if whole_hours > 1 else ''}"
        else:
            return f"{whole_hours} heure{'s' if whole_hours > 1 else ''} {remaining_minutes} minute{'s' if remaining_minutes > 1 else ''}"

    days = int(hours / 24)
    remaining_hours = int(hours % 24)
    return f"{days} jour{'s' if days > 1 else ''} {remaining_hours} heure{'s' if remaining_hours > 1 else ''}"


def estimate_processing_time(video_duration_seconds: float) -> dict[str, float]:
    """
    Estimation du temps de traitement basée sur la durée de la vidéo.

    Returns:
        dict avec:
        - estimated_total: temps total estimé (secondes)
        - estimated_burn_time: temps d'incrustation estimé (secondes)
        - writer_timeout: timeout pour le writer (secondes)
    """
    # Formules basées sur l'analyse des logs existants
    # writer_timeout actuel = duration * 2
    writer_timeout = video_duration_seconds * 2

    # Temps d'incrustation estimé (basé sur observations)
    # ~1.0-1.5x la durée vidéo selon la complexité
    estimated_burn_time = video_duration_seconds * 1.3  # moyenne

    # Temps total estimé (transcription + traduction + burn)
    # Transcription/traduction : ~60-120s fixe
    fixed_processing = 90.0
    estimated_total = fixed_processing + estimated_burn_time

    return {
        "estimated_total_seconds": estimated_total,
        "estimated_burn_seconds": estimated_burn_time,
        "writer_timeout_seconds": writer_timeout,
        "video_duration_seconds": video_duration_seconds,
    }


def _normalize_url(raw_url: str) -> str:
    """
    Normalise une URL source pour le pipeline de traduction.

    - Supprime les espaces superflus
    - Convertit les URLs youtu.be en youtube.com/watch?v=
    - Supprime les trackers (utm_*, si_app, etc.)
    - Nettoie les doublons de paramètres

    Args:
        raw_url: URL brute à normaliser.

    Returns:
        URL normalisée.
    """
    from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

    url = raw_url.strip()

    # youtu.be → youtube.com
    if "youtu.be" in url:
        vid = url.rstrip("/").split("/")[-1].split("?")[0]
        url = f"https://www.youtube.com/watch?v={vid}"

    # Nettoyage des paramètres
    parsed = urlparse(url)
    query_params = parse_qs(parsed.query, keep_blank_values=True)

    # Paramètres à supprimer (trackers, inutiles)
    TRACKER_KEYS = {
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_term",
        "utm_content",
        "si",
        "si_app",
        "feature",
        "pp",
        "fbclid",
        "gclid",
        "ref",
    }
    cleaned = {k: v for k, v in query_params.items() if k not in TRACKER_KEYS}

    # Reconstruire
    new_query = urlencode(cleaned, doseq=True)
    return urlunparse(parsed._replace(query=new_query))
