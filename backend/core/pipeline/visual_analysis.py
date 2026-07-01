"""
pipeline/visual_analysis.py — Analyse visuelle par frames — Subvox

VisualAnalysisStep : extrait des frames de la vidéo et les analyse via
OpenRouter (Gemini Flash) pour décrire le contenu visuel.

Fonctionnement :
1. Détermine l'intervalle d'échantillonnage selon la durée (Tier 1/2/3)
2. Extrait les frames via ffmpeg
3. Encode en base64 et envoie en batch à Gemini Flash
4. Parse la réponse JSON structurée

Modèle principal : google/gemini-3-flash-preview (vision) via OpenRouter
Fallback       : google/gemini-2.5-flash-lite (vision) si le principal échoue
Coût estimé    : ~$0.002-0.01 par vidéo de 10 min
"""

from __future__ import annotations

import asyncio
import base64
import json
from pathlib import Path

from core.logging_setup import get_logger
from core.openrouter import call_openrouter
from core.pipeline.analysis_base import AnalysisStep
from core.pipeline.ffmpeg import _ffmpeg_path, _get_video_duration

logger = get_logger(__name__)


# ─── Modèles ─────────────────────────────────────────────────────────────────

VISUAL_PRIMARY_MODEL = "google/gemini-3-flash-preview"
VISUAL_FALLBACK_MODEL = "google/gemini-2.5-flash-lite"


# ─── Intervalles d'échantillonnage par tier ─────────────────────────────────

def _get_frame_interval(duration_s: float) -> int:
    """
    Retourne l'intervalle en secondes entre chaque frame selon la durée.

    Tier 1 (0-5 min)   : 1 frame / 5s  → max ~60 frames
    Tier 2 (5-20 min)  : 1 frame / 10s → max ~120 frames
    Tier 3 (20-120 min): 1 frame / 30s → max ~240 frames
    """
    if duration_s <= 300:
        return 5  # Tier 1
    elif duration_s <= 1200:
        return 10  # Tier 2
    else:
        return 30  # Tier 3


# ─── Prompts ────────────────────────────────────────────────────────────────

VISUAL_ANALYSIS_SYSTEM_PROMPT = """Tu es un expert en analyse visuelle de vidéos.
À partir d'images clés extraites d'une vidéo, tu décris le contenu visuel.

Pour chaque image, analyse :
- Le lieu (indoor/outdoor, type de pièce/paysage)
- Les objets présents
- Les personnes visibles (nombre approximatif)
- Les plaques d'immatriculation visibles
- Le texte superposé (slides, titres, incrustations)
- Les couleurs dominantes
- Le mouvement caméra (static, pan, zoom)
- Tout contenu sensible (violence, nudité, drogues)

Si une image est illisible (noire, floue, bloquée), indique-le simplement."""


VISUAL_ANALYSIS_USER_TEMPLATE = """J'analyse une vidéo de {duration_s} secondes.
Voici {frame_count} images clés extraites à intervalles réguliers.

Pour chaque image, décris ce que tu vois. Puis fournis une analyse globale.

Images :
{images_section}

Retourne un JSON avec cette structure exacte :
{{
  "scene_count": <int>,
  "global_description": "<string, 2-3 phrases>",
  "sensitive_content_detected": <bool>,
  "sensitive_content_types": ["<string>", ...],
  "scenes": [
    {{
      "start_s": <float>,
      "end_s": <float>,
      "description": "<string>",
      "location": "indoor" | "outdoor" | "unknown",
      "faces_count": <int>,
      "plates_count": <int>,
      "text_overlay_detected": <bool>,
      "camera_movement": "static" | "pan" | "zoom" | "dynamic" | "unknown"
    }}
  ],
  "dominant_colors": ["<hex>", ...],
  "has_text_overlay": <bool>,
  "global_faces_count": <int>,
  "global_plates_count": <int>
}}"""


# ─── Helpers d'extraction de frames ─────────────────────────────────────────


async def _extract_frames(
    video_path: str | Path,
    interval: int,
    max_frames: int = 50,
) -> list[dict]:
    """
    Extrait des frames de la vidéo à intervalle régulier.

    Retourne une liste de dicts : [{"timestamp_s": float, "data": bytes}, ...]
    Limité à max_frames pour éviter de saturer le contexte OpenRouter.
    """
    video = Path(video_path)
    if not video.exists():
        logger.error("Extract frames : vidéo introuvable", extra={"path": str(video)})
        return []

    duration = _get_video_duration(video)
    if not duration or duration <= 0:
        logger.warning("Extract frames : durée invalide, utilisation 60s par défaut")
        duration = 60.0

    ffmpeg = _ffmpeg_path()
    frames: list[dict] = []

    # Calculer les timestamps
    timestamps = list(range(0, int(duration), interval))

    # Limiter le nombre de frames
    if len(timestamps) > max_frames:
        # Échantillonnage uniforme
        step = len(timestamps) / max_frames
        timestamps = [timestamps[int(i * step)] for i in range(max_frames)]

    logger.info(
        "Extraction de frames démarrée",
        extra={
            "video": video.name,
            "duration_s": duration,
            "interval_s": interval,
            "total_frames": len(timestamps),
        },
    )

    for ts in timestamps:
        try:
            frame_data = await _extract_single_frame(ffmpeg, video, ts)
            if frame_data:
                frames.append({"timestamp_s": float(ts), "data": frame_data})
        except Exception as exc:
            logger.warning(
                "Échec extraction frame",
                extra={"timestamp_s": ts, "error": str(exc)},
            )

    logger.info(
        "Extraction de frames terminée",
        extra={"extracted": len(frames), "requested": len(timestamps)},
    )
    return frames


async def _extract_single_frame(
    ffmpeg: str, video: Path, timestamp_s: int
) -> bytes | None:
    """Extrait une frame JPEG à un timestamp donné via ffmpeg."""
    cmd = [
        ffmpeg,
        "-y",
        "-ss", str(timestamp_s),
        "-i", str(video),
        "-vframes", "1",
        "-q:v", "3",  # Qualité JPEG (2-5 est bon)
        "-f", "image2pipe",
        "-",
    ]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30.0)

        if proc.returncode != 0 or not stdout:
            logger.warning(
                "ffmpeg frame extraction échouée",
                extra={
                    "timestamp_s": timestamp_s,
                    "returncode": proc.returncode,
                    "stderr": stderr.decode(errors="replace")[:200],
                },
            )
            return None

        return stdout
    except asyncio.TimeoutError:
        logger.warning("Timeout extraction frame", extra={"timestamp_s": timestamp_s})
        return None
    except Exception as exc:
        logger.warning(
            "Erreur extraction frame",
            extra={"timestamp_s": timestamp_s, "error": str(exc)},
        )
        return None


def _encode_frame_base64(frame_data: bytes) -> str:
    """Encode une frame JPEG en base64 pour OpenRouter."""
    return base64.b64encode(frame_data).decode("utf-8")


# ─── Step ────────────────────────────────────────────────────────────────────


class VisualAnalysisStep(AnalysisStep):
    """
    Analyse visuelle de la vidéo via extraction de frames + Gemini Flash.

    Input :
        video_path (str) — Chemin local vers le fichier vidéo
        duration_s (number) — Durée de la vidéo en secondes

    Output :
        scene_count, global_description, sensitive_content_detected,
        scenes (liste de scènes avec description, location, faces/plates),
        dominant_colors, has_text_overlay, global_faces_count,
        global_plates_count, frames_analyzed
    """

    async def analyze(self, input_data: dict) -> dict:
        video_path = input_data.get("video_path", "")
        duration_s = float(input_data.get("duration_s", 0))
        user_id = input_data.get("user_id", "anonymous")

        if not video_path or not Path(video_path).exists():
            logger.warning("VisualAnalysisStep: vidéo introuvable — skip")
            return self._default_result()

        # 1. Déterminer l'intervalle d'échantillonnage
        interval = _get_frame_interval(duration_s)
        max_frames = 50  # Sécurité : max 50 frames pour le contexte

        # 2. Extraire les frames
        frames = await _extract_frames(video_path, interval, max_frames)
        if not frames:
            logger.warning("VisualAnalysisStep: aucune frame extraite — skip")
            return self._default_result()

        # 3. Envoyer les frames au modèle principal (avec fallback)
        result = await self._analyze_frames(frames, duration_s, user_id)
        result["frames_analyzed"] = len(frames)

        logger.info(
            "VisualAnalysis terminée",
            extra={
                "frames": len(frames),
                "scenes": result.get("scene_count", 0),
                "faces": result.get("global_faces_count", 0),
                "sensitive": result.get("sensitive_content_detected", False),
            },
        )
        return result

    async def _analyze_frames(
        self, frames: list[dict], duration_s: float, user_id: str
    ) -> dict:
        """Envoie les frames au modèle vision avec fallback si le modèle principal échoue."""
        # Préparer le message avec les frames encodées en base64
        vision_messages: list[dict] = []

        # Message système
        vision_messages.append(
            {"role": "system", "content": VISUAL_ANALYSIS_SYSTEM_PROMPT}
        )

        # Message utilisateur avec images
        user_content: list[dict] = []

        # Texte d'introduction
        frame_count = len(frames)
        intro_text = VISUAL_ANALYSIS_USER_TEMPLATE.format(
            duration_s=duration_s,
            frame_count=frame_count,
            images_section="(images intégrées ci-dessous)",
        )
        user_content.append({"type": "text", "text": intro_text})

        # Ajouter les frames (max 15 pour ne pas saturer le contexte)
        frames_to_send = frames[:15]

        for i, frame in enumerate(frames_to_send):
            b64_data = _encode_frame_base64(frame["data"])
            ts = frame["timestamp_s"]
            user_content.append(
                {
                    "type": "text",
                    "text": f"\n--- Image {i+1} à t={ts}s ---",
                }
            )
            user_content.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{b64_data}",
                    },
                }
            )

        vision_messages.append({"role": "user", "content": user_content})

        # ── Tentative avec le modèle principal ──
        result = await self._try_call(
            vision_messages, VISUAL_PRIMARY_MODEL, frames, frames_to_send, duration_s, user_id
        )
        if result is not None:
            return result

        # ── Fallback avec le modèle secondaire ──
        logger.warning(
            "VisualAnalysisStep: fallback vers modèle secondaire",
            extra={"fallback_model": VISUAL_FALLBACK_MODEL, "user_id": user_id[:8]},
        )
        result = await self._try_call(
            vision_messages, VISUAL_FALLBACK_MODEL, frames, frames_to_send, duration_s, user_id
        )
        if result is not None:
            return result

        # ── Les deux modèles ont échoué ──
        logger.error(
            "VisualAnalysisStep: modèles principal ET fallback échoués — retour défauts",
            extra={
                "primary": VISUAL_PRIMARY_MODEL,
                "fallback": VISUAL_FALLBACK_MODEL,
                "user_id": user_id[:8],
            },
        )
        result = self._default_result()
        result["frames_extracted"] = len(frames)
        result["frames_analyzed"] = 0
        return result

    async def _try_call(
        self,
        vision_messages: list[dict],
        model: str,
        frames: list[dict],
        frames_to_send: list[dict],
        duration_s: float,
        user_id: str,
    ) -> dict | None:
        """
        Tente un appel OpenRouter avec le modèle donné.
        Retourne le résultat parsé si succès, None si échec.
        """
        try:
            raw_response = await call_openrouter(
                messages=vision_messages,
                model=model,
                temperature=0.3,
                max_tokens=4096,
                user_id=user_id,
                cache_key=f"visual_analysis|{model}|{len(frames)}frames|{duration_s}s",
            )

            # call_openrouter retourne (content | None, tokens_in, tokens_out)
            result_text = raw_response[0] if isinstance(raw_response, tuple) else raw_response

            if not result_text:
                logger.warning(
                    "VisualAnalysisStep: réponse OpenRouter vide",
                    extra={"model": model, "user_id": user_id[:8]},
                )
                return None

            # Extraire les métriques tokens/cost si disponibles
            tokens_in = raw_response[1] if isinstance(raw_response, tuple) and len(raw_response) > 1 else 0
            tokens_out = raw_response[2] if isinstance(raw_response, tuple) and len(raw_response) > 2 else 0

            logger.info(
                "VisualAnalysis: réponse reçue",
                extra={
                    "model": model,
                    "frames_sent": len(frames_to_send),
                    "frames_total": len(frames),
                    "tokens_in": tokens_in,
                    "tokens_out": tokens_out,
                    "user_id": user_id[:8],
                },
            )

            # Parser la réponse
            result = self._parse_response(result_text, frames)

            # Ajouter des méta-données
            result["frames_extracted"] = len(frames)
            result["frames_analyzed"] = len(frames_to_send)
            result["model_used"] = model

            return result

        except Exception as exc:
            logger.warning(
                "VisualAnalysisStep: appel modèle échoué",
                extra={"error": str(exc), "model": model, "user_id": user_id[:8]},
            )
            import traceback
            logger.warning(
                "VisualAnalysisStep: traceback",
                extra={"traceback": traceback.format_exc()},
            )
            return None

    def _parse_response(self, text: str, frames: list[dict]) -> dict:
        """Parse la réponse JSON du modèle vision."""
        try:
            cleaned = text.strip()
            if "```json" in cleaned:
                cleaned = cleaned.split("```json")[1].split("```")[0].strip()
            elif "```" in cleaned:
                cleaned = cleaned.split("```")[1].split("```")[0].strip()

            result = json.loads(cleaned)

            # Valider les champs obligatoires
            if "scene_count" not in result:
                result["scene_count"] = len(result.get("scenes", []))

            # Convertir les timestamps des scènes si nécessaire
            for scene in result.get("scenes", []):
                if "start_s" not in scene:
                    scene["start_s"] = 0.0
                if "end_s" not in scene:
                    scene["end_s"] = 0.0

            return result

        except (json.JSONDecodeError, IndexError, TypeError):
            logger.warning(
                "VisualAnalysisStep: réponse JSON invalide — utilisation défauts",
                extra={"response_preview": text[:300]},
            )
            return self._default_result()

    def _default_result(self) -> dict:
        return {
            "scene_count": 0,
            "global_description": "",
            "sensitive_content_detected": False,
            "sensitive_content_types": [],
            "scenes": [],
            "dominant_colors": [],
            "has_text_overlay": False,
            "global_faces_count": 0,
            "global_plates_count": 0,
            "frames_extracted": 0,
            "frames_analyzed": 0,
            "model_used": VISUAL_PRIMARY_MODEL,
        }

    def get_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "video_path": {
                    "type": "string",
                    "description": "Chemin local vers le fichier vidéo source",
                },
                "duration_s": {
                    "type": "number",
                    "description": "Durée de la vidéo en secondes",
                },
                "user_id": {
                    "type": "string",
                    "description": "ID utilisateur pour tracking OpenRouter",
                },
            },
            "required": ["video_path", "duration_s"],
        }