"""
Étape 1 : Téléchargement de la vidéo source.
"""

from __future__ import annotations

import html
from pathlib import Path

from core.config import settings
from core.logging_setup import get_logger
from core.pipeline.ffmpeg import (
    _get_video_dims,
    _get_video_duration,
    _get_video_frames,
)
from core.pipeline.cookies import _is_valid_cookies_file
from core.pipeline.steps._helpers import _get_tmp
from core.pipeline.steps._types import StepResult

logger = get_logger(__name__)


async def step_download(
    job_id: str,
    source_url: str,
    cookies_file: str = "",
    download_only: bool = False,
) -> StepResult:
    """
    Télécharge la vidéo source via yt-dlp.
    Extrait métadonnées (durée, langue, thumbnail, width, height).
    Upload source vers Supabase si configuré.
    """
    from core.supabase_storage import upload_video as _upload_video

    log_extra = {"job_id": job_id}
    tmp = _get_tmp(job_id)
    tmp.mkdir(parents=True, exist_ok=True)
    source_mp4 = tmp / "source.mp4"

    # ── Fichier local (upload direct) — pas de yt-dlp ──────────────
    if source_url.startswith("file://"):
        local_path = source_url.replace("file://", "")
        src = Path(local_path)
        if not src.exists():
            return StepResult(success=False, error=f"Fichier introuvable: {local_path}")
        # Copier vers le dossier de travail
        import shutil
        shutil.copy2(src, source_mp4)
        logger.info(f"Fichier local copié: {local_path} → {source_mp4}", extra=log_extra)
        # Métadonnées minimales
        from core.pipeline.ffmpeg import _get_video_dims as _get_dims, _get_video_duration as _get_dur
        duration = _get_dur(source_mp4)
        width, height = _get_dims(source_mp4)
        return StepResult(success=True, data={
            "source_mp4": str(source_mp4),
            "duration_s": duration,
            "width": width,
            "height": height,
            "title": src.stem,  # Nom du fichier comme titre provisoire
            "upload_local": True,
        })

    import yt_dlp

    logger.info(f"Telechargement {source_url}", extra=log_extra)

    ydl_opts: dict = {
        "format": "best[ext=mp4]/best",
        "outtmpl": str(source_mp4),
        "quiet": True,
        "no_warnings": True,
        "retries": 3,
        "ignoreerrors": False,
        "socket_timeout": 30,
    }

    browser_used = False
    if cookies_file:
        if _is_valid_cookies_file(cookies_file):
            ydl_opts["cookiefile"] = cookies_file
            logger.info(f"Cookies depuis fichier: {cookies_file}", extra=log_extra)
        else:
            logger.warning(
                f"Fichier cookies invalide ou vide: {cookies_file}",
                extra=log_extra,
            )
    else:
        # Fallback: cookie partagé depuis le volume economy/cache
        _default_cookies = "/app/.cache/youtube_cookies.txt"
        if _is_valid_cookies_file(_default_cookies):
            ydl_opts["cookiefile"] = _default_cookies
            logger.info(f"Cookies depuis fallback: {_default_cookies}", extra=log_extra)

    try:
        import browser_cookie3

        ydl_opts["cookiesfrombrowser"] = ("chrome", None, None, None)
        logger.info("Cookies depuis navigateur Chrome", extra=log_extra)
        browser_used = True
    except ImportError:
        pass

    if not cookies_file and not browser_used:
        logger.warning(
            "Aucun cookie disponible -- telechargement public uniquement",
            extra=log_extra,
        )

    duration = 0.0
    source_lang = ""
    thumbnail_url = None
    video_type = "long"
    source_storage_url = None
    video_title = ""
    video_description = ""

    import json, subprocess, os

    # Check if video already exists in storage from a previous job
    existing_source = None
    source_storage_url = None
    try:
        from core.db import direct_connect as _dc
        import asyncio
        async def _find_existing():
            async with _dc() as conn:
                row = await conn.fetchrow(
                    "SELECT source_storage_url FROM jobs "
                    "WHERE source_url=$1 AND status='done' "
                    "AND source_storage_url IS NOT NULL "
                    "ORDER BY created_at DESC LIMIT 1",
                    source_url,
                )
                return row["source_storage_url"] if row else None
        existing_source = asyncio.run(_find_existing())
    except Exception:
        pass

    if existing_source:
        # Copy existing file instead of downloading from YouTube
        import shutil
        existing_path = existing_source.replace("file://", "")
        if os.path.exists(existing_path):
            shutil.copy2(existing_path, source_mp4)
            logger.info(
                f"Vidéo réutilisée depuis storage: {existing_path}",
                extra=log_extra,
            )
            source_storage_url = existing_source
            # Get metadata from existing file
            probe_cmd = ["ffprobe", "-v", "error", "-show_entries",
                         "format=duration:format=size", "-of",
                         "default=noprint_wrappers=1:nokey=1",
                         str(source_mp4)]
            probe = subprocess.run(probe_cmd, capture_output=True, timeout=30, text=True)
            lines = probe.stdout.strip().split("\n")
            duration = float(lines[0]) if lines else 0

    if not existing_source:
        cookies_arg = ydl_opts.get("cookiefile", "")
        base_cmd = [
            "yt-dlp",
            "--remote-components", "ejs:github",
            "--no-warnings",
            "--retries", "3",
            "--socket-timeout", "30",
            "--sleep-requests", "1.0",
            "--sleep-interval", "3",
            "--max-sleep-interval", "10",
        ]
        if cookies_arg:
            base_cmd += ["--cookies", cookies_arg]

        # 1. Get JSON metadata (no download)
        r_info = subprocess.run(
            base_cmd + ["--dump-json", source_url],
            capture_output=True, timeout=30, text=True,
        )
        if r_info.returncode != 0:
            r_info = subprocess.run(
                [c for c in base_cmd if c not in ("--remote-components", "ejs:github")]
                + ["--dump-json", source_url],
                capture_output=True, timeout=30, text=True,
            )
        if r_info.returncode != 0:
            raise RuntimeError(f"yt-dlp metadata failed: {r_info.stderr[:500]}")

        info = {}
        for line in r_info.stdout.strip().split("\n"):
            line = line.strip()
            if line and line.startswith("{"):
                try:
                    info = json.loads(line)
                    break
                except json.JSONDecodeError:
                    continue
        if not info.get("duration"):
            raise RuntimeError(f"yt-dlp metadata empty: {r_info.stderr[:200]}")

        # 2. Download the video
        dl_cmd = base_cmd + ["-f", "best[height<=1080]", "-o", str(source_mp4), source_url]
        r_dl = subprocess.run(dl_cmd, capture_output=True, timeout=7200, text=True)
        if r_dl.returncode != 0 or not source_mp4.exists():
            raise RuntimeError(f"yt-dlp download failed: {r_dl.stderr[:500] if r_dl.stderr else 'unknown'}")

        duration = float(info.get("duration") or 0)
        source_lang = (info.get("language") or info.get("original_lang") or "").lower()[:5]
        thumbnail_url = info.get("thumbnail")
        video_type = "short" if duration <= settings.VIDEO_SHORT_MAX_SECONDS else "long"
        video_title = html.unescape(info.get("title", "") or "")
        video_description = html.unescape(info.get("description", "") or "")
    if video_title:
        from core.db import direct_connect as _dc
        try:
            async with _dc() as c:
                await c.execute(
                    "UPDATE jobs SET title=$1, updated_at=now() WHERE id=$2 AND title IS NULL",
                    video_title[:500], __import__("uuid").UUID(job_id),
                )
        except Exception:
            pass
    if thumbnail_url:
            logger.debug(f"Thumbnail extrait: {thumbnail_url[:80]}", extra=log_extra)

    # Métriques vidéo
    video_width, video_height = 0, 0
    video_frame_rate = 0.0
    video_file_size_mb = 0.0
    video_format = "mp4"
    try:
        video_width, video_height = _get_video_dims(source_mp4)
        vid_dur = _get_video_duration(source_mp4) or duration
        vid_frames = _get_video_frames(source_mp4) or 0
        video_frame_rate = round(vid_frames / vid_dur, 2) if vid_dur > 0 else 0.0
        video_file_size_mb = round(source_mp4.stat().st_size / (1024 * 1024), 2)
        video_format = source_mp4.suffix.lstrip(".").lower() or "mp4"
    except Exception:
        pass

    logger.info(
        f"Download OK: {duration:.1f}s -- type: {video_type} "
        f"({video_width}x{video_height} {video_format} {video_file_size_mb}MB)",
        extra=log_extra,
    )

        # Upload source vers stockage local
    if source_mp4.exists():
        try:
            source_upload_res = await _upload_video(
                str(job_id), source_mp4, filename=f"source_{job_id}.mp4"
            )
            if source_upload_res:
                source_storage_url = source_upload_res["storage_url"]
                logger.info(
                    f"Source uploadee: {source_storage_url[:80]}", extra=log_extra
                )
        except Exception as e:
            logger.error(f"Upload source echoue: {e}", extra=log_extra)
        if not source_storage_url or source_storage_url.startswith("file://"):
            # Fallback local (dev mode, no Supabase) — use /storage/ URL
            import shutil
            storage_dir = Path(__file__).resolve().parent.parent.parent.parent.parent / "storage"
            storage_dir.mkdir(parents=True, exist_ok=True)
            local_path = storage_dir / f"source_{job_id}.mp4"
            if not local_path.exists():
                shutil.copy2(str(source_mp4), str(local_path))
            source_storage_url = f"http://127.0.0.1:8000/storage/source_{job_id}.mp4"
            logger.info(f"Source sauvegardee localement: {source_storage_url}", extra=log_extra)

    # Vérification taille max
    if duration > settings.VIDEO_MAX_SECONDS:
        raise ValueError(
            f"Video trop longue: {duration:.0f}s (max {settings.VIDEO_MAX_SECONDS}s)"
        )

    # Si download_only, upload final et on termine
    if download_only:
        from core.supabase_storage import upload_video as _upload_video2

        storage_key = f"download_{job_id}.mp4"
        upload_res = await _upload_video2(
            f"download_{job_id}",
            source_mp4,
            filename=f"download_{job_id}.mp4",
        )
        if upload_res:
            storage_key = upload_res.get("storage_url", storage_key)
            logger.info("Download mode termine", extra=log_extra)
        return StepResult(
            data={
                "storage_url": storage_key,
                "summary": "",
                "source_lang": source_lang,
                "duration_s": duration,
                "video_type": video_type,
                "thumbnail_url": thumbnail_url,
                "source_storage_url": source_storage_url or "",
            }
        )

    # Catégorie vidéo enrichie
    from core.pipeline.eta import compute_video_category

    video_category = compute_video_category(duration)

    return StepResult(
        data={
            "duration_s": duration,
            "source_lang": source_lang,
            "thumbnail_url": thumbnail_url or "",
            "video_type": video_type,
            "video_category": video_category,
            "source_storage_url": source_storage_url or "",
            "video_title": video_title,
            "video_description": video_description,
            "width": video_width,
            "height": video_height,
            "frame_rate": video_frame_rate,
            "file_size_mb": video_file_size_mb,
            "format": video_format,
            "codec": video_format,
        },
        files={"source_mp4": str(source_mp4)},
    )