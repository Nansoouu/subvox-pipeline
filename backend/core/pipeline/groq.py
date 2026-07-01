"""
pipeline/groq.py — Transcription via Groq API (Whisper) — Subvox

Améliorations v2 :
  - Vérification du quota avant chaque appel API
  - Timeout adaptatif (30s + durée_audio × 2)
  - Rotation intelligente des clés (évite celles en rate-limit)
  - Messages d'erreur structurés avec temps restant connu
  - Rapport de consommation au service economy
"""

import subprocess
from pathlib import Path

from core.logging_setup import get_logger
from core.pipeline.ffmpeg import _ffmpeg_path

logger = get_logger(__name__)

_GROQ_CHUNK_DURATION = 600  # 10 min par chunk
_ECONOMY_TIMEOUT = 5        # timeout pour les appels de vérification


# ─── Vérification de quota ───────────────────────────────────────────────────


def _check_key_quota(api_key: str, economy_url: str | None = None) -> dict:
    """
    Interroge le service economy pour savoir si cette clé a du temps restant.

    Retourne un dict avec :
      { "has_quota": bool, "remaining_s": int, "daily_limit_s": int, "daily_usage_s": int }
    En cas d'erreur (économie injoignable, pas d'URL), retourne un dict
    avec has_quota=True pour ne pas bloquer la transcription.
    """
    if not economy_url:
        return {"has_quota": True, "remaining_s": 7200, "daily_limit_s": 7200, "daily_usage_s": 0}

    import httpx as _httpx

    key_short = api_key[:8] + "..."
    try:
        resp = _httpx.get(
            f"{economy_url}/billing/groq-key/check-quota",
            params={"key_prefix": api_key[:16]},
            timeout=_ECONOMY_TIMEOUT,
        )
        if resp.status_code == 200:
            data = resp.json()
            remaining = data.get("remaining_s", 7200)
            daily_limit = data.get("daily_limit_s", 7200)
            daily_usage = data.get("daily_usage_s", 0)
            has_quota = remaining > 10  # au moins 10s de marge
            logger.debug(
                "Groq quota check",
                extra={
                    "key": key_short,
                    "remaining_s": remaining,
                    "limit_s": daily_limit,
                    "has_quota": has_quota,
                },
            )
            return {
                "has_quota": has_quota,
                "remaining_s": remaining,
                "daily_limit_s": daily_limit,
                "daily_usage_s": daily_usage,
            }
        logger.warning(
            "Groq quota check failed",
            extra={"key": key_short, "status": resp.status_code},
        )
    except Exception as e:
        logger.warning(
            "Groq quota check exception (economy unreachable?)",
            extra={"error": str(e)},
        )
    # En cas de doute, laisser passer
    return {"has_quota": True, "remaining_s": 7200, "daily_limit_s": 7200, "daily_usage_s": 0}


def _report_groq_usage(api_key: str, duration_s: int, economy_url: str | None = None) -> None:
    """Signale au service economy le temps consommé par cette clé."""
    if not economy_url:
        return
    import httpx as _httpx

    try:
        _httpx.post(
            f"{economy_url}/billing/groq-key/report-usage",
            json={"key_prefix": api_key[:16], "duration_s": duration_s},
            timeout=_ECONOMY_TIMEOUT,
        )
    except Exception:
        pass  # non bloquant


def _compute_timeout(audio_duration_s: float) -> float:
    """
    Calcule un timeout adaptatif pour l'appel Groq.
    Base : 30s + durée_audio × 2, plafonné à 600s, minimum 120s.
    """
    raw = 30.0 + audio_duration_s * 2.0
    return max(120.0, min(600.0, raw))


# ─── Appel Groq avec suivi de quota ──────────────────────────────────────────


def _transcribe_via_groq(
    video_path: Path,
    srt_out: Path,
    txt_out: Path,
    api_key: str,
    economy_url: str | None = None,
) -> dict | None:
    """
    Transcription via Groq API.
    Gestion avancée : rotation de clés, quota check, chunking, checkpoint, retry.

    Retourne None si échec définitif, sinon un dict avec text/language.
    En cas de quota épuisé, retourne un dict avec error="quota_exhausted"
    et un message explicite.
    """
    import httpx as _httpx
    import json as _json
    import time as _time

    ffmpeg = _ffmpeg_path()
    audio_path = video_path.parent / f"{video_path.stem}_audio.mp3"

    # ── 1. Parsing des clés ──────────────────────────────────────────────────
    raw_keys = [k.strip() for k in api_key.split(",") if k.strip()] if api_key else []
    if not raw_keys:
        logger.error("Aucune clé API Groq configurée")
        return None

    # Dédoublonner en gardant l'ordre
    api_keys = list(dict.fromkeys(raw_keys))

    # ── 2. Pré-vérification des quotas ────────────────────────────────────────
    key_quota_cache: dict[str, dict] = {}
    for k in api_keys:
        quota = _check_key_quota(k, economy_url)
        key_quota_cache[k] = quota
        if not quota["has_quota"]:
            logger.warning(
                f"Clé {k[:8]}... quota épuisé "
                f"({quota['daily_usage_s']}/{quota['daily_limit_s']}s)"
            )

    # Si toutes les clés sont hors quota, message clair
    if all(not key_quota_cache[k]["has_quota"] for k in api_keys):
        used = key_quota_cache[api_keys[0]]["daily_usage_s"]
        limit = key_quota_cache[api_keys[0]]["daily_limit_s"]
        msg = (
            f"Temps Groq épuisé ({used}/{limit}s). "
            "Ajoute ta propre clé Groq dans Mon compte pour débloquer 1h30 par jour."
        )
        logger.warning(msg)
        return {"error": "quota_exhausted", "message": msg}

    def _call_groq_once(audio_bytes: bytes, filename: str, key: str, timeout_s: float):
        try:
            with _httpx.Client(timeout=timeout_s) as client:
                resp = client.post(
                    "https://api.groq.com/openai/v1/audio/transcriptions",
                    headers={"Authorization": f"Bearer {key}"},
                    files={"file": (filename, audio_bytes, "audio/mpeg")},
                    data={
                        "model": "whisper-large-v3-turbo",
                        "response_format": "verbose_json",
                        "timestamp_granularities[]": "segment",
                    },
                )
            if resp.status_code == 429:
                return "rate_limit"
            if resp.status_code == 401:
                return "invalid_key"
            if resp.status_code != 200:
                logger.error(
                    "Groq HTTP error",
                    extra={"status": resp.status_code, "detail": resp.text[:300]},
                )
                return None
            return resp.json()
        except _httpx.TimeoutException:
            logger.warning(f"Groq timeout ({timeout_s}s) pour {filename}")
            return "timeout"
        except Exception as e:
            logger.error("Groq API exception", extra={"error": str(e)})
            return None

    def _call_groq_with_retry(
        audio_bytes: bytes,
        filename: str,
        audio_duration_s: float,
        chunk_idx: int = 0,
    ):
        """
        Rotation intelligente : essaie chaque clé en round-robin,
        mais saute celles qui étaient en quota épuisé ou en erreur.
        """
        timeout_s = _compute_timeout(audio_duration_s)
        n = len(api_keys)
        failed_keys: set[int] = set()
        rate_limited_keys: set[int] = set()

        for attempt in range(n * 3):  # 3 passes max
            idx = (chunk_idx + attempt) % n
            if idx in failed_keys:
                continue

            key = api_keys[idx]
            key_tag = f"clé {idx + 1}/{n}"

            # Vérification rapide du quota (cache)
            quota = key_quota_cache.get(key)
            if quota and not quota["has_quota"]:
                logger.debug(f"{key_tag} sautée (quota épuisé)")
                failed_keys.add(idx)
                continue

            result = _call_groq_once(audio_bytes, filename, key, timeout_s)

            if result == "rate_limit":
                logger.warning(f"{key_tag} rate limit — 65s d'attente")
                rate_limited_keys.add(idx)
                _time.sleep(65)
                continue
            if result == "invalid_key":
                logger.warning(f"{key_tag} clé invalide (401)")
                failed_keys.add(idx)
                continue
            if result == "timeout":
                logger.warning(f"{key_tag} timeout ({timeout_s}s)")
                rate_limited_keys.add(idx)
                continue
            if result is not None:
                return result, idx

            failed_keys.add(idx)

        # Toutes les clés épuisées
        logger.error(f"Groq : toutes les clés épuisées pour {filename}")
        return None, 0

    # ── 3. Log des clés disponibles ───────────────────────────────────────────
    key_count = len(api_keys)
    key_preview = api_keys[0][:8] + "..."
    keys_with_quota = sum(
        1 for k in api_keys if key_quota_cache.get(k, {}).get("has_quota", True)
    )
    logger.info(
        "Groq transcription start",
        extra={
            "video": str(video_path.name),
            "keys_total": key_count,
            "keys_with_quota": keys_with_quota,
            "key_preview": key_preview,
        },
    )

    try:
        # ── 4. Extraction audio ────────────────────────────────────────────────
        logger.info("Extraction audio via FFmpeg", extra={"video": str(video_path.name)})
        r = subprocess.run(
            [
                ffmpeg,
                "-y",
                "-i",
                str(video_path),
                "-vn",
                "-ar",
                "16000",
                "-ac",
                "1",
                "-b:a",
                "16k",
                str(audio_path),
            ],
            capture_output=True,
            timeout=7200,
        )
        if r.returncode != 0 or not audio_path.exists():
            logger.error("Extraction audio échouée", extra={"returncode": r.returncode})
            return None

        audio_size_mb = audio_path.stat().st_size / 1024 / 1024
        logger.info(f"Audio extrait : {audio_size_mb:.2f} MB")

        def _to_srt_time(seconds: float) -> str:
            h = int(seconds // 3600)
            m = int((seconds % 3600) // 60)
            s = int(seconds % 60)
            ms = int((seconds - int(seconds)) * 1000)
            return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

        # ── 5. Chemin rapide : audio ≤ 24 MB ─────────────────────────────────
        if audio_size_mb <= 24:
            logger.info(
                "Groq appel API (audio ≤ 24MB)",
                extra={"size_mb": round(audio_size_mb, 1)},
            )
            with open(audio_path, "rb") as f:
                audio_bytes = f.read()

            # Durée estimée via rapport taille/taux (16kbps mono 16kHz)
            estimated_duration_s = audio_path.stat().st_size / (16000 * 2)  # ≈ 16KB/s

            data, used_key_idx = _call_groq_with_retry(
                audio_bytes, audio_path.name, estimated_duration_s, chunk_idx=0
            )
            if not data:
                return None
            if isinstance(data, dict) and data.get("error") == "quota_exhausted":
                return data

            segments = data.get("segments", [])
            full_text = data.get("text", "").strip()
            language = data.get("language", "en")

            if not segments and not full_text:
                return None

            # Rapporter la consommation
            total_duration_s = segments[-1]["end"] if segments else estimated_duration_s
            _report_groq_usage(api_keys[used_key_idx], int(total_duration_s), economy_url)

            if not segments:
                srt_out.write_text(
                    f"1\n00:00:00,000 --> 00:00:05,000\n{full_text}\n",
                    encoding="utf-8",
                )
                txt_out.write_text(full_text, encoding="utf-8")
                return {"text": full_text, "language": language}

            srt_lines, text_parts = [], []
            for i, seg in enumerate(segments, 1):
                start = float(seg.get("start", 0))
                end = float(seg.get("end", start + 2))
                text = seg.get("text", "").strip()
                if not text:
                    continue
                text_parts.append(text)
                srt_lines.append(
                    f"{i}\n{_to_srt_time(start)} --> {_to_srt_time(end)}\n{text}\n"
                )

            full_text = " ".join(text_parts)
            srt_out.write_text("\n".join(srt_lines), encoding="utf-8")
            txt_out.write_text(full_text, encoding="utf-8")
            logger.info(
                f"Groq transcription OK: {len(srt_lines)} segments",
                extra={"language": language},
            )
            return {"text": full_text, "language": language}

        # ── 6. Audio > 24 MB → chunking + checkpoint ─────────────────────────
        ffprobe = ffmpeg.replace("ffmpeg", "ffprobe")
        r2 = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(audio_path),
            ],
            capture_output=True,
            timeout=30,
        )
        try:
            total_s = float(r2.stdout.decode().strip())
        except Exception:
            total_s = 7200.0

        n_chunks = max(1, -(-int(total_s) // _GROQ_CHUNK_DURATION))
        logger.info(
            f"Groq chunking: {n_chunks} chunk(s) x{_GROQ_CHUNK_DURATION // 60}min",
            extra={
                "audio_mb": round(audio_size_mb, 1),
                "duration_s": total_s,
                "n_keys": len(api_keys),
            },
        )

        all_segs: list[tuple[float, float, str]] = []
        language = "en"
        last_key_idx = 0
        total_consumed_s = 0

        for ci in range(n_chunks):
            offset_s = ci * _GROQ_CHUNK_DURATION
            chunk_json_path = video_path.parent / f"chunk_{ci}.json"

            # Checkpoint
            if chunk_json_path.exists():
                try:
                    saved = _json.loads(chunk_json_path.read_text(encoding="utf-8"))
                    loaded = [(d["s"], d["e"], d["t"]) for d in saved if d.get("t")]
                    if loaded:
                        all_segs.extend(loaded)
                        logger.info(
                            f"Groq checkpoint chunk {ci + 1}/{n_chunks}: {len(loaded)} segs"
                        )
                        continue
                except Exception:
                    pass

            # Découpage chunk
            chunk_mp3 = video_path.parent / f"chunk_{ci}.mp3"
            rc = subprocess.run(
                [
                    ffmpeg,
                    "-y",
                    "-ss",
                    str(offset_s),
                    "-t",
                    str(_GROQ_CHUNK_DURATION),
                    "-i",
                    str(audio_path),
                    "-ac",
                    "1",
                    "-ar",
                    "16000",
                    "-b:a",
                    "16k",
                    str(chunk_mp3),
                ],
                capture_output=True,
                timeout=300,
            )
            if rc.returncode != 0 or not chunk_mp3.exists():
                logger.warning(
                    f"Groq chunk {ci + 1}/{n_chunks} découpage échoué, skip"
                )
                continue

            chunk_mb = chunk_mp3.stat().st_size / 1024 / 1024
            logger.info(
                f"Groq chunk {ci + 1}/{n_chunks} "
                f"({chunk_mb:.1f} MB, offset={offset_s:.0f}s)"
            )

            with open(chunk_mp3, "rb") as f:
                chunk_bytes = f.read()
            chunk_mp3.unlink(missing_ok=True)

            data, last_key_idx = _call_groq_with_retry(
                chunk_bytes,
                f"chunk_{ci}.mp3",
                float(_GROQ_CHUNK_DURATION),
                chunk_idx=last_key_idx,
            )
            if not data:
                logger.warning(
                    f"Groq chunk {ci + 1} transcription échouée, skip"
                )
                continue
            if isinstance(data, dict) and data.get("error") == "quota_exhausted":
                # Quota épuisé en cours de route
                logger.warning(
                    f"Groq chunk {ci + 1}: quota épuisé, "
                    f"on garde {len(all_segs)} segments déjà obtenus"
                )
                break

            language = data.get("language", language)
            chunk_segs: list[tuple[float, float, str]] = []
            for seg in data.get("segments") or []:
                s = float(seg.get("start", 0)) + offset_s
                e = float(seg.get("end", s + 2)) + offset_s
                t = seg.get("text", "").strip()
                if t:
                    chunk_segs.append((s, e, t))

            all_segs.extend(chunk_segs)
            total_consumed_s += int(_GROQ_CHUNK_DURATION)

            if chunk_segs:
                chunk_json_path.write_text(
                    _json.dumps(
                        [{"s": s, "e": e, "t": t} for s, e, t in chunk_segs],
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )
            logger.info(
                f"Groq chunk {ci + 1}/{n_chunks} : {len(chunk_segs)} segments"
            )

        if not all_segs:
            return None

        # Rapport de consommation
        _report_groq_usage(api_keys[last_key_idx], total_consumed_s, economy_url)

        # Fusion finale
        srt_lines, text_parts = [], []
        for idx, (s, e, t) in enumerate(all_segs, 1):
            srt_lines.append(f"{idx}\n{_to_srt_time(s)} --> {_to_srt_time(e)}\n{t}\n")
            text_parts.append(t)

        full_text = " ".join(text_parts)
        srt_out.write_text("\n".join(srt_lines), encoding="utf-8")
        txt_out.write_text(full_text, encoding="utf-8")

        for ci in range(n_chunks):
            (video_path.parent / f"chunk_{ci}.json").unlink(missing_ok=True)

        logger.info(
            f"Groq fusion finale: {len(srt_lines)} segments",
            extra={"language": language},
        )
        return {"text": full_text, "language": language}

    except Exception:
        logger.exception("Groq transcription error")
        return None
    finally:
        audio_path.unlink(missing_ok=True)
