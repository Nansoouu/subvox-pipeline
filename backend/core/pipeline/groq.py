"""
pipeline/groq.py — Transcription via Groq API (Whisper) — Subvox
"""

import subprocess
from pathlib import Path

from core.logging_setup import get_logger
from core.pipeline.ffmpeg import _ffmpeg_path

logger = get_logger(__name__)

# Duree max d'un chunk en secondes (10 min = 600s)
_GROQ_CHUNK_DURATION = 600


def _transcribe_via_groq(
    video_path: Path,
    srt_out: Path,
    txt_out: Path,
    api_key: str,
) -> dict | None:
    """
    Transcription via Groq API.
    Gestion avancee : rotation de cles, chunking, checkpoint, retry 429.
    """
    import httpx as _httpx
    import json as _json
    import time as _time

    ffmpeg = _ffmpeg_path()
    audio_path = video_path.parent / f"{video_path.stem}_audio.mp3"

    # Rotation de cles
    api_keys = [k.strip() for k in api_key.split(",") if k.strip()] if api_key else []
    if not api_keys:
        logger.error("Aucune cle API Groq configuree")
        return None

    def _call_groq_once(audio_bytes: bytes, filename: str, key: str):
        try:
            with _httpx.Client(timeout=300.0) as client:
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
            if resp.status_code != 200:
                logger.error(
                    "Groq HTTP error",
                    extra={"status": resp.status_code, "detail": resp.text[:300]},
                )
                return None
            return resp.json()
        except Exception as e:
            logger.error("Groq API exception", extra={"error": str(e)})
            return None

    def _call_groq_with_retry(audio_bytes: bytes, filename: str, chunk_idx: int = 0):
        n = len(api_keys)
        for attempt in range(n * 2):
            key = api_keys[(chunk_idx + attempt) % n]
            key_tag = f"cle {(chunk_idx + attempt) % n + 1}/{n}"
            result = _call_groq_once(audio_bytes, filename, key)
            if result == "rate_limit":
                logger.warning(f"Groq 429 rate limit ({key_tag}) -- attente 65s")
                _time.sleep(65)
                continue
            if result is not None:
                return result, (chunk_idx + attempt) % n
        logger.error(f"Groq toutes les cles epuisees pour {filename}")
        return None, 0

    # Log présence clé API (masquée)
    key_count = len(api_keys)
    key_preview = api_keys[0][:8] + "..." if api_keys else "aucune"
    logger.info(
        "Groq transcription start",
        extra={
            "video": str(video_path.name),
            "keys_count": key_count,
            "key_preview": key_preview,
        },
    )

    try:
        # Extraction audio
        logger.info(
            "Extraction audio via FFmpeg", extra={"video": str(video_path.name)}
        )
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
            logger.error("Extraction audio echouee", extra={"returncode": r.returncode})
            return None

        audio_size_mb = audio_path.stat().st_size / 1024 / 1024
        logger.info(f"Audio extrait : {audio_size_mb:.2f} MB")

        def _to_srt_time(seconds: float) -> str:
            h = int(seconds // 3600)
            m = int((seconds % 3600) // 60)
            s = int(seconds % 60)
            ms = int((seconds - int(seconds)) * 1000)
            return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

        # Chemin rapide : audio <= 24 MB
        if audio_size_mb <= 24:
            logger.info(
                "Groq appel API (audio <= 24MB)",
                extra={"size_mb": round(audio_size_mb, 1)},
            )
            with open(audio_path, "rb") as f:
                audio_bytes = f.read()

            data, _ = _call_groq_with_retry(audio_bytes, audio_path.name, chunk_idx=0)
            if not data:
                return None

            segments = data.get("segments", [])
            full_text = data.get("text", "").strip()
            language = data.get("language", "en")

            if not segments and not full_text:
                return None

            if not segments:
                srt_out.write_text(
                    f"1\n00:00:00,000 --> 00:00:05,000\n{full_text}\n", encoding="utf-8"
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

        # Audio > 24 MB -> chunking + checkpoint
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
            f"Groq chunking: {n_chunks} chunk(s) x{_GROQ_CHUNK_DURATION//60}min",
            extra={
                "audio_mb": round(audio_size_mb, 1),
                "duration_s": total_s,
                "n_keys": len(api_keys),
            },
        )

        all_segs: list[tuple[float, float, str]] = []
        language = "en"
        last_key_idx = 0

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
                            f"Groq checkpoint chunk {ci+1}/{n_chunks}: {len(loaded)} segs"
                        )
                        continue
                except Exception:
                    pass

            # Decoupage chunk
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
                logger.warning(f"Groq chunk {ci+1}/{n_chunks} decoupage echoue, skip")
                continue

            chunk_mb = chunk_mp3.stat().st_size / 1024 / 1024
            logger.info(
                f"Groq chunk {ci+1}/{n_chunks} ({chunk_mb:.1f} MB, offset={offset_s:.0f}s)"
            )

            with open(chunk_mp3, "rb") as f:
                chunk_bytes = f.read()
            chunk_mp3.unlink(missing_ok=True)

            data, last_key_idx = _call_groq_with_retry(
                chunk_bytes, f"chunk_{ci}.mp3", chunk_idx=last_key_idx
            )
            if not data:
                logger.warning(f"Groq chunk {ci+1} transcription echouee, skip")
                continue

            language = data.get("language", language)
            chunk_segs: list[tuple[float, float, str]] = []
            for seg in data.get("segments") or []:
                s = float(seg.get("start", 0)) + offset_s
                e = float(seg.get("end", s + 2)) + offset_s
                t = seg.get("text", "").strip()
                if t:
                    chunk_segs.append((s, e, t))

            all_segs.extend(chunk_segs)

            if chunk_segs:
                chunk_json_path.write_text(
                    _json.dumps(
                        [{"s": s, "e": e, "t": t} for s, e, t in chunk_segs],
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )
            logger.info(f"Groq chunk {ci+1}/{n_chunks} : {len(chunk_segs)} segments")

        if not all_segs:
            return None

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
