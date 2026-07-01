"""
pipeline/groq.py — Transcription via Groq API (Whisper) — Subvox

Améliorations v2 :
  - Vérification du quota avant chaque appel API
  - Timeout adaptatif (30s + durée_audio × 2)
  - Rotation intelligente des clés (évite celles en rate-limit)
  - Messages d'erreur structurés avec temps restant connu
  - Rapport de consommation au service economy
  - Retour des segments structurés avec confiance (avg_logprob, no_speech_prob)
"""

import subprocess
from pathlib import Path

from core.logging_setup import get_logger
from core.pipeline.ffmpeg import _ffmpeg_path

logger = get_logger(__name__)

_GROQ_CHUNK_DURATION = 600  # 10 min par chunk
_ECONOMY_TIMEOUT = 5        # timeout pour les appels de vérification


# ─── Vérification de quota ───────────────────────────────────────────────────


def _check_key_quota(
    api_key: str,
    economy_url: str | None = None,
    expected_duration_s: float = 10.0,
) -> dict:
    """
    Interroge le service economy pour savoir si cette clé a assez de temps
    pour couvrir `expected_duration_s` secondes de transcription.

    expected_duration_s : durée prévue du chunk (défaut 10s).
    Un chunk de 600s nécessite >= 600s restants.

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
            # Vérification stricte : assez de temps pour le chunk entier
            has_quota = remaining >= expected_duration_s
            logger.debug(
                "Groq quota check",
                extra={
                    "key": key_short,
                    "remaining_s": remaining,
                    "expected_s": expected_duration_s,
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


# ─── Helpers de parsing ──────────────────────────────────────────────────────


def _whisper_segment_to_dict(seg: dict, offset_s: float = 0.0) -> dict:
    """
    Transforme un segment Whisper (verbose_json) en dict structuré propre.

    Inclut les métriques de confiance : avg_logprob, no_speech_prob, compression_ratio.
    """
    start = float(seg.get("start", 0)) + offset_s
    end = float(seg.get("end", start + 2)) + offset_s
    text = seg.get("text", "").strip()
    return {
        "start_s": round(start, 3),
        "end_s": round(end, 3),
        "text": text,
        "confidence": round(float(seg.get("avg_logprob", 0) or 0), 4),
        "no_speech_prob": round(float(seg.get("no_speech_prob", 0) or 0), 4),
        "compression_ratio": round(float(seg.get("compression_ratio", 1) or 1), 4),
        "tokens": seg.get("tokens", []),
        "temperature": float(seg.get("temperature", 0)),
    }


def _build_segments_list(
    raw_segments: list[dict],
    language: str,
    offset_s: float = 0.0,
) -> list[dict]:
    """
    Construit une liste de segments structurés propre à partir des segments Whisper bruts.
    Filtre les segments vides, ajoute l'index et la langue.
    """
    result = []
    for i, seg in enumerate(raw_segments, 1):
        d = _whisper_segment_to_dict(seg, offset_s)
        if not d["text"]:
            continue
        d["index"] = i
        d["language"] = language
        result.append(d)
    return result


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

    Retourne un dict structuré :
      {
        "text": str,           # Texte brut complet
        "language": str,       # Langue détectée
        "segments": [          # Segments structurés avec confiance
          {"index": int, "start_s": float, "end_s": float, "text": str,
           "confidence": float, "no_speech_prob": float, ...}
        ],
        "model": str,          # Modèle utilisé
      }

    Retourne None si échec définitif.
    En cas de quota épuisé, retourne {"error": "quota_exhausted", "message": "..."}.
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

    api_keys = list(dict.fromkeys(raw_keys))

    # ── 2. Pré-vérification des quotas ────────────────────────────────────────
    chunk_duration_s = _GROQ_CHUNK_DURATION
    key_quota_cache: dict[str, dict] = {}
    for k in api_keys:
        quota = _check_key_quota(k, economy_url, expected_duration_s=chunk_duration_s)
        key_quota_cache[k] = quota
        if not quota["has_quota"]:
            remaining = quota["remaining_s"]
            logger.warning(
                f"Clé {k[:8]}... quota insuffisant pour un chunk de "
                f"{chunk_duration_s}s (reste {remaining}s)"
            )

    if all(not key_quota_cache[k]["has_quota"] for k in api_keys):
        used = key_quota_cache[api_keys[0]]["daily_usage_s"]
        limit = key_quota_cache[api_keys[0]]["daily_limit_s"]
        remaining = key_quota_cache[api_keys[0]]["remaining_s"]
        if remaining > 0:
            msg = (
                f"Temps Groq insuffisant pour transcrire un bloc de "
                f"{chunk_duration_s // 60}min. "
                f"Il te reste {remaining // 60}min ({used}/{limit}s). "
                "Ajoute ta propre clé Groq dans Mon compte pour débloquer 1h30 par jour."
            )
        else:
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
        timeout_s = _compute_timeout(audio_duration_s)
        n = len(api_keys)
        failed_keys: set[int] = set()
        rate_limited_keys: set[int] = set()

        for attempt in range(n * 3):
            idx = (chunk_idx + attempt) % n
            if idx in failed_keys:
                continue

            key = api_keys[idx]
            key_tag = f"clé {idx + 1}/{n}"

            quota = key_quota_cache.get(key)
            if quota and not quota["has_quota"]:
                logger.debug(f"{key_tag} sautée (quota insuffisant pour le chunk)")
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

            estimated_duration_s = audio_path.stat().st_size / (16000 * 2)

            data, used_key_idx = _call_groq_with_retry(
                audio_bytes, audio_path.name, estimated_duration_s, chunk_idx=0
            )
            if not data:
                return None
            if isinstance(data, dict) and data.get("error") == "quota_exhausted":
                return data

            raw_segments = data.get("segments", [])
            full_text = data.get("text", "").strip()
            language = data.get("language", "en")

            if not raw_segments and not full_text:
                return None

            # Structurer les segments
            segments = _build_segments_list(raw_segments, language)
            total_duration_s = max((s["end_s"] for s in segments), default=estimated_duration_s)
            _report_groq_usage(api_keys[used_key_idx], int(total_duration_s), economy_url)

            # Générer SRT + TXT (rétrocompatibilité)
            if not segments:
                srt_out.write_text(
                    f"1\n00:00:00,000 --> 00:00:05,000\n{full_text}\n",
                    encoding="utf-8",
                )
                txt_out.write_text(full_text, encoding="utf-8")
            else:
                srt_lines, text_parts = [], []
                for seg in segments:
                    text_parts.append(seg["text"])
                    srt_lines.append(
                        f"{seg['index']}\n{_to_srt_time(seg['start_s'])} "
                        f"--> {_to_srt_time(seg['end_s'])}\n{seg['text']}\n"
                    )
                full_text = " ".join(text_parts)
                srt_out.write_text("\n".join(srt_lines), encoding="utf-8")
                txt_out.write_text(full_text, encoding="utf-8")

            logger.info(
                f"Groq transcription OK: {len(segments)} segments",
                extra={"language": language},
            )
            return {
                "text": full_text,
                "language": language,
                "segments": segments,
                "model": data.get("model", "whisper-large-v3-turbo"),
            }

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

        all_segments: list[dict] = []
        language = "en"
        last_key_idx = 0
        total_consumed_s = 0
        seg_counter = 0

        for ci in range(n_chunks):
            offset_s = ci * _GROQ_CHUNK_DURATION
            chunk_json_path = video_path.parent / f"chunk_{ci}.json"

            # Checkpoint
            if chunk_json_path.exists():
                try:
                    saved = _json.loads(chunk_json_path.read_text(encoding="utf-8"))
                    if saved:
                        all_segments.extend(saved)
                        seg_counter = max((s["index"] for s in saved), default=0)
                        logger.info(
                            f"Groq checkpoint chunk {ci + 1}/{n_chunks}: {len(saved)} segs"
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
                logger.warning(f"Groq chunk {ci + 1}/{n_chunks} découpage échoué, skip")
                continue

            chunk_mb = chunk_mp3.stat().st_size / 1024 / 1024
            logger.info(
                f"Groq chunk {ci + 1}/{n_chunks} ({chunk_mb:.1f} MB, offset={offset_s:.0f}s)"
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
                logger.warning(f"Groq chunk {ci + 1} transcription échouée, skip")
                continue
            if isinstance(data, dict) and data.get("error") == "quota_exhausted":
                logger.warning(
                    f"Groq chunk {ci + 1}: quota épuisé, "
                    f"garde {len(all_segments)} segments déjà obtenus"
                )
                break

            language = data.get("language", language)
            raw_segs = data.get("segments") or []
            chunk_segs = _build_segments_list(raw_segs, language, offset_s)
            # Réindexer globalement
            for s in chunk_segs:
                seg_counter += 1
                s["index"] = seg_counter

            all_segments.extend(chunk_segs)
            total_consumed_s += int(_GROQ_CHUNK_DURATION)

            if chunk_segs:
                chunk_json_path.write_text(
                    _json.dumps(chunk_segs, ensure_ascii=False),
                    encoding="utf-8",
                )
            logger.info(f"Groq chunk {ci + 1}/{n_chunks} : {len(chunk_segs)} segments")

        if not all_segments:
            return None

        _report_groq_usage(api_keys[last_key_idx], total_consumed_s, economy_url)

        # Fusion finale
        srt_lines, text_parts = [], []
        for seg in all_segments:
            text_parts.append(seg["text"])
            srt_lines.append(
                f"{seg['index']}\n{_to_srt_time(seg['start_s'])} "
                f"--> {_to_srt_time(seg['end_s'])}\n{seg['text']}\n"
            )

        full_text = " ".join(text_parts)
        srt_out.write_text("\n".join(srt_lines), encoding="utf-8")
        txt_out.write_text(full_text, encoding="utf-8")

        for ci in range(n_chunks):
            (video_path.parent / f"chunk_{ci}.json").unlink(missing_ok=True)

        logger.info(
            f"Groq fusion finale: {len(all_segments)} segments",
            extra={"language": language},
        )
        return {
            "text": full_text,
            "language": language,
            "segments": all_segments,
            "model": "whisper-large-v3-turbo",
        }

    except Exception:
        logger.exception("Groq transcription error")
        return None
    finally:
        audio_path.unlink(missing_ok=True)
