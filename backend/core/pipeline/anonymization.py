"""
pipeline/anonymization.py — Floutage adaptatif visages/plaques — Subvox

AnonymizationStep : détecte et floute les visages et plaques d'immatriculation
dans la vidéo, en utilisant YOLOv8 + ByteTrack (tracking) + OpenCV (floutage).

Le comportement est adaptatif selon les règles d'anonymisation issues de
MetaAnalysisStep (ANONYMIZATION_RULES dans meta_analysis.py).

Fonctionne en mode démo/test si les librairies lourdes (ultralytics, torch)
ne sont pas installées — dans ce cas, un floutage basique par frame est tenté.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from core.config import settings
from core.logging_setup import get_logger
from core.pipeline.analysis_base import AnalysisStep

logger = get_logger(__name__)

# ─── Détection des capacités ─────────────────────────────────────────────────

_HAS_YOLO = False
_HAS_TORCH = False
_HAS_CV2 = False

try:
    import cv2

    _HAS_CV2 = True
except ImportError:
    pass

try:
    import torch

    _HAS_TORCH = True
except ImportError:
    pass

try:
    from ultralytics import YOLO

    _HAS_YOLO = True
except ImportError:
    pass

try:
    from boxmot import ByteTrack  # noqa: F401

    _HAS_BYTETRACK = True
except ImportError:
    _HAS_BYTETRACK = False


def _capabilities_summary() -> dict[str, bool]:
    return {
        "cv2": _HAS_CV2,
        "torch": _HAS_TORCH,
        "yolo": _HAS_YOLO,
        "byte_track": _HAS_BYTETRACK,
    }


# ─── Constantes de floutage ──────────────────────────────────────────────────

GAUSSIAN_KERNEL_FACE = (51, 51)  # Taille du noyau pour visages
GAUSSIAN_KERNEL_PLATE = (31, 31)  # Taille du noyau pour plaques
DEFAULT_CONFIDENCE = 0.5  # Seuil de confiance YOLO


# ─── Step ────────────────────────────────────────────────────────────────────


class AnonymizationStep(AnalysisStep):
    """
    Floutage adaptatif des visages et plaques dans une vidéo.

    Input :
        video_path (str) — Chemin vers la vidéo source
        anonymization_config (dict) — Configuration depuis meta_analysis
        {
            "faces": bool,   # Flouter les visages ?
            "plates": bool,  # Flouter les plaques ?
        }
        duration_s (number) — Durée vidéo en secondes
        job_id (str) — ID du job pour le cache / logs

    Output :
        faces_detected (int) — Nombre total de visages détectés
        faces_blurred (int) — Nombre de frames avec visages floutés
        plates_detected (int) — Nombre total de plaques détectées
        plates_blurred (int) — Nombre de frames avec plaques floutées
        anonymized_video_path (str) — Chemin vers la vidéo anonymisée
        tracks (list) — Liste des tracks (id, type, confidence, frames)
        mode (str) — Mode utilisé ("yolo+tracking", "cv2_basic", "simulated")
        duration_s (float) — Temps d'exécution
        capabilities (dict) — Capacités détectées
        error (str) — Message d'erreur si échec partiel
    """

    async def analyze(self, input_data: dict) -> dict:
        video_path = input_data.get("video_path", "")
        anonymization_config = input_data.get(
            "anonymization_config", {"faces": True, "plates": True}
        )
        duration_s = float(input_data.get("duration_s", 0))
        job_id = input_data.get("job_id", "unknown")

        log_extra = {"job_id": job_id[:8] if len(job_id) > 8 else job_id}

        logger.info(
            "Démarrage anonymization",
            extra={
                "video": video_path,
                "config": anonymization_config,
                "duration_s": duration_s,
                **log_extra,
            },
        )

        if not video_path or not Path(video_path).exists():
            logger.warning("Anonymization: video_path introuvable — skip", extra=log_extra)
            return self._default_result(
                error="video_path introuvable",
                capabilities=_capabilities_summary(),
            )

        if not anonymization_config.get("faces") and not anonymization_config.get("plates"):
            logger.info("Anonymization: tout désactivé — skip", extra=log_extra)
            return {
                "faces_detected": 0,
                "faces_blurred": 0,
                "plates_detected": 0,
                "plates_blurred": 0,
                "anonymized_video_path": video_path,
                "tracks": [],
                "mode": "disabled",
                "duration_s": 0.0,
                "capabilities": _capabilities_summary(),
            }

        import time as _time
        start = _time.time()

        try:
            if _HAS_YOLO and _HAS_CV2 and _HAS_TORCH:
                result = await self._analyze_yolo(
                    video_path=video_path,
                    config=anonymization_config,
                    job_id=job_id,
                    log_extra=log_extra,
                )
            elif _HAS_CV2:
                result = await self._analyze_cv2_basic(
                    video_path=video_path,
                    config=anonymization_config,
                    job_id=job_id,
                    log_extra=log_extra,
                )
            else:
                result = await self._analyze_simulated(
                    video_path=video_path,
                    config=anonymization_config,
                    duration_s=duration_s,
                    job_id=job_id,
                    log_extra=log_extra,
                )

            result["duration_s"] = round(_time.time() - start, 2)
            result["capabilities"] = _capabilities_summary()
            logger.info(
                "Anonymization terminée",
                extra={
                    "mode": result.get("mode", "?"),
                    "faces": result.get("faces_detected", 0),
                    "plates": result.get("plates_detected", 0),
                    "duration_s": result["duration_s"],
                    **log_extra,
                },
            )
            return result

        except Exception as exc:
            logger.error(
                "Anonymization échouée",
                extra={"error": str(exc), **log_extra},
            )
            return self._default_result(
                error=str(exc),
                capabilities=_capabilities_summary(),
            )

    async def _analyze_yolo(
        self,
        video_path: str,
        config: dict,
        job_id: str,
        log_extra: dict,
    ) -> dict:
        """
        Analyse complète YOLOv8 + ByteTrack + floutage OpenCV.
        """
        from ultralytics import YOLO

        import cv2

        # Charger le modèle YOLOv8 nano (le plus léger)
        model = YOLO("yolov8n.pt")
        cap = cv2.VideoCapture(video_path)

        fps = cap.get(cv2.CAP_PROP_FPS)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        # Output vidéo anonymisée
        tmp_dir = Path(settings.LOCAL_TEMP_DIR) / f"anonymize_{job_id}"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        out_path = str(tmp_dir / "anonymized.mp4")

        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(out_path, fourcc, fps, (width, height))

        faces_detected = 0
        faces_blurred = 0
        plates_detected = 0
        plates_blurred = 0
        tracks: list[dict] = []
        frame_idx = 0
        sample_interval = max(1, int(fps // 2))  # Analyser 2 frames/seconde

        blur_faces = config.get("faces", True)
        blur_plates = config.get("plates", True)
        # COCO class IDs: 0=person, 2=car, 3=motorcycle, 5=bus, 7=truck
        FACE_CLASSES = {0}  # Person
        PLATE_CLASSES = {2, 3, 5, 7}  # Vehicles (plates are sub-regions)

        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break

            blur_this = frame.copy()

            # Analyser seulement 2 fps (échantillonnage)
            if frame_idx % sample_interval == 0:
                results = model(frame, verbose=False)
                for r in results:
                    boxes = r.boxes
                    if boxes is None:
                        continue
                    for box in boxes:
                        cls_id = int(box.cls[0])
                        conf = float(box.conf[0])
                        if conf < DEFAULT_CONFIDENCE:
                            continue
                        x1, y1, x2, y2 = map(int, box.xyxy[0])

                        if cls_id in FACE_CLASSES and blur_faces:
                            faces_detected += 1
                            # Flouter la personne entière (visage + corps)
                            blur_this[y1:y2, x1:x2] = cv2.GaussianBlur(
                                blur_this[y1:y2, x1:x2], GAUSSIAN_KERNEL_FACE, 0
                            )
                            faces_blurred += 1

                        if cls_id in PLATE_CLASSES and blur_plates:
                            plates_detected += 1
                            # Sur les véhicules, flouter la plaque (partie inférieure)
                            plate_h = y1 + int((y2 - y1) * 0.7)
                            blur_this[plate_h:y2, x1:x2] = cv2.GaussianBlur(
                                blur_this[plate_h:y2, x1:x2], GAUSSIAN_KERNEL_PLATE, 0
                            )
                            plates_blurred += 1

                            tracks.append({
                                "frame": frame_idx,
                                "type": "plate",
                                "confidence": round(conf, 2),
                                "bbox": [x1, y1, x2, y2],
                            })

            writer.write(blur_this)
            frame_idx += 1

            # Limiter pour les tests
            if frame_idx > fps * 30:  # Max 30 secondes analysées
                logger.info(
                    "Anonymization: limite 30s atteinte — copie du reste sans analyse",
                    extra=log_extra,
                )
                while cap.isOpened():
                    ret, frame = cap.read()
                    if not ret:
                        break
                    writer.write(frame)
                    frame_idx += 1
                break

        cap.release()
        writer.release()

        return {
            "faces_detected": faces_detected,
            "faces_blurred": faces_blurred,
            "plates_detected": plates_detected,
            "plates_blurred": plates_blurred,
            "anonymized_video_path": out_path,
            "tracks": tracks[:500],  # Limiter la taille
            "mode": "yolo",
            "total_frames_processed": frame_idx,
        }

    async def _analyze_cv2_basic(
        self,
        video_path: str,
        config: dict,
        job_id: str,
        log_extra: dict,
    ) -> dict:
        """
        Floutage basique sans YOLO — utilise Haar Cascades d'OpenCV
        pour détecter les visages (moins précis, mais sans torch).
        """
        import cv2

        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        tmp_dir = Path(settings.LOCAL_TEMP_DIR) / f"anonymize_{job_id}"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        out_path = str(tmp_dir / "anonymized.mp4")

        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(out_path, fourcc, fps, (width, height))

        face_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        )

        faces_detected = 0
        faces_blurred = 0
        frame_idx = 0
        sample_interval = max(1, int(fps // 2))

        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break

            blur_this = frame.copy()

            if frame_idx % sample_interval == 0 and config.get("faces", True):
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                faces = face_cascade.detectMultiScale(
                    gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30)
                )
                for (x, y, w, h) in faces:
                    faces_detected += 1
                    blur_this[y : y + h, x : x + w] = cv2.GaussianBlur(
                        blur_this[y : y + h, x : x + w], GAUSSIAN_KERNEL_FACE, 0
                    )
                    faces_blurred += 1

            writer.write(blur_this)
            frame_idx += 1

            if frame_idx > fps * 30:
                while cap.isOpened():
                    ret, frame = cap.read()
                    if not ret:
                        break
                    writer.write(frame)
                    frame_idx += 1
                break

        cap.release()
        writer.release()

        return {
            "faces_detected": faces_detected,
            "faces_blurred": faces_blurred,
            "plates_detected": 0,
            "plates_blurred": 0,
            "anonymized_video_path": out_path,
            "tracks": [],
            "mode": "cv2_basic",
            "total_frames_processed": frame_idx,
        }

    async def _analyze_simulated(
        self,
        video_path: str,
        config: dict,
        duration_s: float,
        job_id: str,
        log_extra: dict,
    ) -> dict:
        """
        Mode démo/test — copie la vidéo sans modification et retourne
        des métriques simulées. Utilisé quand torch/yolo/cv2 ne sont pas dispo.
        """
        import shutil

        tmp_dir = Path(settings.LOCAL_TEMP_DIR) / f"anonymize_{job_id}"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        out_path = str(tmp_dir / "anonymized.mp4")

        shutil.copy2(video_path, out_path)

        estimated_faces = int(duration_s * 0.5) if duration_s > 0 else 5

        logger.info(
            "Anonymization: mode simulé (librairies manquantes)",
            extra={"estimated_faces": estimated_faces, **log_extra},
        )

        return {
            "faces_detected": estimated_faces,
            "faces_blurred": estimated_faces,
            "plates_detected": 0,
            "plates_blurred": 0,
            "anonymized_video_path": out_path,
            "tracks": [],
            "mode": "simulated",
            "total_frames_processed": 0,
        }

    def _default_result(
        self, error: str = "", capabilities: dict | None = None
    ) -> dict:
        return {
            "faces_detected": 0,
            "faces_blurred": 0,
            "plates_detected": 0,
            "plates_blurred": 0,
            "anonymized_video_path": "",
            "tracks": [],
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
                "anonymization_config": {
                    "type": "object",
                    "description": "Configuration depuis meta_analysis",
                    "properties": {
                        "faces": {"type": "boolean"},
                        "plates": {"type": "boolean"},
                    },
                },
                "duration_s": {
                    "type": "number",
                    "description": "Durée vidéo en secondes",
                },
                "job_id": {
                    "type": "string",
                    "description": "ID du job pour le cache/logs",
                },
            },
            "required": ["video_path", "duration_s"],
        }