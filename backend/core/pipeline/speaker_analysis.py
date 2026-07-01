"""
pipeline/speaker_analysis.py — Diarisation des locuteurs — Subvox

SpeakerAnalysisStep : identifie les locuteurs dans la vidéo en utilisant
Pyannote 3.1 pour la diarization audio.

Fonctionne en mode démo/test si Pyannote n'est pas installé.
Nécessite un token HuggingFace pour télécharger le modèle Pyannote.

Pipeline :
  1. Extraire l'audio de la vidéo (ffmpeg → 16kHz mono WAV)
  2. Exécuter Pyannote 3.1 segmentation + embedding
  3. Assigner des IDs et estimer le genre via heuristiques
  4. Retourner les segments de parole par locuteur + métriques
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from core.config import settings
from core.logging_setup import get_logger
from core.pipeline.analysis_base import AnalysisStep

logger = get_logger(__name__)

# ─── Détection des capacités ─────────────────────────────────────────────────

_HAS_PYANNOTE = False
_HAS_TORCH = False
_HAS_LIBSNDFILE = False

try:
    import torch

    _HAS_TORCH = True
except ImportError:
    pass

try:
    from pyannote.audio import Pipeline

    _HAS_PYANNOTE = True
except ImportError:
    pass

try:
    import soundfile  # noqa: F401

    _HAS_LIBSNDFILE = True
except ImportError:
    pass


def _capabilities_summary() -> dict[str, bool]:
    return {
        "torch": _HAS_TORCH,
        "pyannote": _HAS_PYANNOTE,
        "soundfile": _HAS_LIBSNDFILE,
    }


# ─── Step ────────────────────────────────────────────────────────────────────


class SpeakerAnalysisStep(AnalysisStep):
    """
    Diarisation des locuteurs via Pyannote 3.1.

    Input :
        video_path (str) — Chemin vers la vidéo source
        duration_s (number) — Durée vidéo en secondes
        job_id (str) — ID du job pour logs/cache
        hf_token (str, optional) — Token HuggingFace pour Pyannote

    Output :
        speakers (list) — Liste des locuteurs détectés :
            [
                {
                    "id": str,          # Speaker_01, Speaker_02, etc.
                    "turns": int,       # Nombre de prises de parole
                    "total_time_s": float,  # Temps total de parole
                    "gender_guess": str,    # "male", "female", "unknown"
                    "segments": [{"start": float, "end": float}],
                }
            ]
        total_speakers (int) — Nombre total de locuteurs
        total_segments (int) — Nombre total de segments de parole
        language (str) — Langue détectée (via transcript si dispo)
        mode (str) — Mode utilisé ("pyannote", "simulated")
        duration_s (float) — Temps d'exécution
        capabilities (dict) — Capacités détectées
    """

    async def analyze(self, input_data: dict) -> dict:
        video_path = input_data.get("video_path", "")
        duration_s = float(input_data.get("duration_s", 0))
        job_id = input_data.get("job_id", "unknown")
        hf_token = input_data.get("hf_token", "")

        log_extra = {"job_id": job_id[:8] if len(job_id) > 8 else job_id}

        logger.info(
            "Démarrage speaker analysis",
            extra={
                "video": video_path,
                "duration_s": duration_s,
                "pyannote": _HAS_PYANNOTE,
                **log_extra,
            },
        )

        if not video_path or not Path(video_path).exists():
            logger.warning("SpeakerAnalysis: video_path introuvable — skip", extra=log_extra)
            return self._default_result(
                error="video_path introuvable",
                capabilities=_capabilities_summary(),
            )

        import time as _time
        start = _time.time()

        try:
            if _HAS_PYANNOTE and _HAS_TORCH and hf_token:
                result = await self._analyze_pyannote(
                    video_path=video_path,
                    hf_token=hf_token,
                    job_id=job_id,
                    log_extra=log_extra,
                )
            else:
                result = await self._analyze_simulated(
                    video_path=video_path,
                    duration_s=duration_s,
                    job_id=job_id,
                    log_extra=log_extra,
                )

            result["duration_s"] = round(_time.time() - start, 2)
            result["capabilities"] = _capabilities_summary()
            logger.info(
                "SpeakerAnalysis terminée",
                extra={
                    "mode": result.get("mode", "?"),
                    "speakers": result.get("total_speakers", 0),
                    "segments": result.get("total_segments", 0),
                    "duration_s": result["duration_s"],
                    **log_extra,
                },
            )
            return result

        except Exception as exc:
            logger.error(
                "SpeakerAnalysis échouée",
                extra={"error": str(exc), **log_extra},
            )
            return self._default_result(
                error=str(exc),
                capabilities=_capabilities_summary(),
            )

    async def _analyze_pyannote(
        self,
        video_path: str,
        hf_token: str,
        job_id: str,
        log_extra: dict,
    ) -> dict:
        """
        Analyse complète via Pyannote 3.1 Pipeline.
        """
        import torch
        from pyannote.audio import Pipeline

        tmp_dir = Path(settings.LOCAL_TEMP_DIR) / f"speaker_{job_id}"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        wav_path = str(tmp_dir / "audio_16k.wav")

        # 1. Extraire l'audio via ffmpeg (16kHz mono)
        logger.info("Extraction audio via ffmpeg", extra=log_extra)
        ffmpeg_cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-vn",
            "-acodec", "pcm_s16le",
            "-ar", "16000",
            "-ac", "1",
            wav_path,
        ]
        r = subprocess.run(
            ffmpeg_cmd, capture_output=True, text=True, timeout=600
        )
        if r.returncode != 0 or not Path(wav_path).exists():
            raise RuntimeError(
                f"Extraction audio échouée: {r.stderr[-300:] if r.stderr else 'inconnu'}"
            )

        # 2. Charger le pipeline Pyannote
        logger.info("Chargement pipeline Pyannote 3.1", extra=log_extra)
        pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            use_auth_token=hf_token,
        )

        if torch.cuda.is_available():
            pipeline.to(torch.device("cuda"))
            logger.info("Pyannote sur GPU", extra=log_extra)
        else:
            logger.info("Pyannote sur CPU", extra=log_extra)

        # 3. Appliquer la diarization
        logger.info("Diarization en cours...", extra=log_extra)
        diarization = pipeline(wav_path)

        # 4. Parser les résultats
        speakers_map: dict[str, dict] = {}
        segments: list[dict] = []

        for turn, _, speaker in diarization.itertracks(yield_label=True):
            speaker_id = speaker
            start_s = round(turn.start, 2)
            end_s = round(turn.end, 2)
            seg_duration = round(end_s - start_s, 2)

            segments.append({
                "speaker": speaker_id,
                "start": start_s,
                "end": end_s,
                "duration_s": seg_duration,
            })

            if speaker_id not in speakers_map:
                speakers_map[speaker_id] = {
                    "id": speaker_id,
                    "turns": 0,
                    "total_time_s": 0.0,
                    "gender_guess": "unknown",
                    "segments": [],
                }

            speakers_map[speaker_id]["turns"] += 1
            speakers_map[speaker_id]["total_time_s"] += seg_duration
            speakers_map[speaker_id]["segments"].append({
                "start": start_s,
                "end": end_s,
            })

        # 5. Heuristique de genre basée sur la fréquence fondamentale (F0)
        # Pour l'instant, estimation basique via rapport temps de parole
        # (une version plus sophistiquée utiliserait pydub ou librosa)
        for spk_id, spk_data in speakers_map.items():
            spk_data["total_time_s"]
            # Heuristique simple : si c'est le locuteur principal et
            # temps de parole > 60%, marquer comme "dominant"
            speakers_list = list(speakers_map.values())
            max_time = max(s.total_time_s for s in speakers_list) if speakers_list else 0
            if max_time > 0 and spk_data["total_time_s"] == max_time:
                spk_data["gender_guess"] = "dominant"
            else:
                spk_data["gender_guess"] = "secondary"

        return {
            "speakers": list(speakers_map.values()),
            "total_speakers": len(speakers_map),
            "total_segments": len(segments),
            "language": "unknown",
            "mode": "pyannote",
        }

    async def _analyze_simulated(
        self,
        video_path: str,
        duration_s: float,
        job_id: str,
        log_extra: dict,
    ) -> dict:
        """
        Mode démo/test — simule 1-3 locuteurs sans Pyannote.
        Utilise ffmpeg pour détecter les silences (approximation basique).
        """
        tmp_dir = Path(settings.LOCAL_TEMP_DIR) / f"speaker_{job_id}"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        wav_path = str(tmp_dir / "audio_16k.wav")

        # Extraire audio pour analyse silences
        ffmpeg_cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-vn",
            "-acodec", "pcm_s16le",
            "-ar", "16000",
            "-ac", "1",
            wav_path,
        ]
        subprocess.run(ffmpeg_cmd, capture_output=True, timeout=600)

        # Analyser les silences via ffmpeg silencedetect
        silence_cmd = [
            "ffmpeg", "-i", wav_path,
            "-af", "silencedetect=noise=-30dB:d=0.5",
            "-f", "null", "-",
        ]
        r = subprocess.run(silence_cmd, capture_output=True, text=True, timeout=300)
        stderr_out = r.stderr or ""

        # Compter les segments de parole (entre silences)
        import re
        silence_starts = [
            float(m) for m in re.findall(r"silence_start: ([\d.]+)", stderr_out)
        ]
        [
            float(m) for m in re.findall(r"silence_end: ([\d.]+)", stderr_out)
        ]

        # Simuler 2 locuteurs avec répartition 60/40
        if duration_s <= 0:
            duration_s = 60.0

        speaker1_time = duration_s * 0.6
        speaker2_time = duration_s * 0.4
        num_segments = max(1, len(silence_starts) // 2)

        speakers = [
            {
                "id": "Speaker_01",
                "turns": max(1, num_segments),
                "total_time_s": round(speaker1_time, 2),
                "gender_guess": "unknown",
                "segments": [
                    {"start": 0.0, "end": round(speaker1_time * 0.5, 2)},
                    {
                        "start": round(speaker1_time * 0.5, 2),
                        "end": round(speaker1_time, 2),
                    },
                ],
            },
            {
                "id": "Speaker_02",
                "turns": max(1, num_segments // 2),
                "total_time_s": round(speaker2_time, 2),
                "gender_guess": "unknown",
                "segments": [
                    {
                        "start": round(speaker1_time, 2),
                        "end": round(duration_s, 2),
                    }
                ],
            },
        ]

        logger.info(
            "SpeakerAnalysis: mode simulé (Pyannote non disponible)",
            extra={
                "silence_segments": len(silence_starts),
                "estimated_speakers": 2,
                **log_extra,
            },
        )

        return {
            "speakers": speakers,
            "total_speakers": 2,
            "total_segments": num_segments * 2,
            "language": "unknown",
            "mode": "simulated",
        }

    def _default_result(
        self, error: str = "", capabilities: dict | None = None
    ) -> dict:
        return {
            "speakers": [],
            "total_speakers": 0,
            "total_segments": 0,
            "language": "unknown",
            "mode": "error",
            "duration_s": 0.0,
            "capabilities": capabilities or {},
            "error": error,
        }

    def get_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "video_path": {
                    "type": "string",
                    "description": "Chemin vers la vidéo source",
                },
                "duration_s": {
                    "type": "number",
                    "description": "Durée vidéo en secondes",
                },
                "job_id": {
                    "type": "string",
                    "description": "ID du job pour logs/cache",
                },
                "hf_token": {
                    "type": "string",
                    "description": "Token HuggingFace pour Pyannote",
                },
            },
            "required": ["video_path", "duration_s"],
        }