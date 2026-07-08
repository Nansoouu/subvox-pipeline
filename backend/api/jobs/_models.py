"""
api/jobs/_models.py — Classes Pydantic partagées + constantes
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel

from core.openrouter import SUBTITLE_LANG_NAMES

VALID_LANGS = set(SUBTITLE_LANG_NAMES.keys())

STATUS_PROGRESS = {
    "queued": 5,
    "downloading": 15,
    "transcribing": 35,
    "translating": 60,
    "burning": 80,
    "uploading": 92,
    "done": 100,
    "error": 0,
}

STATUS_LABEL = {
    "queued": "En attente dans la file…",
    "downloading": "Téléchargement de la vidéo…",
    "transcribing": "Transcription audio en cours…",
    "translating": "Traduction des sous-titres…",
    "burning": "Rendu vidéo final…",
    "uploading": "Finalisation…",
    "done": "Terminé !",
    "error": "Erreur",
}

# Temps moyen estimé par vidéo (secondes) — utilisé pour la file d'attente
AVG_PROCESSING_S = 240  # ~4 min


class JobSubmitRequest(BaseModel):
    source_url: str
    target_lang: str
    mode: str = "translate"  # "download" ou "translate"
    original_filename: Optional[str] = None
    visitor_token: Optional[str] = None  # UUID string pour les sessions anonymes
    total_langs: int = 1  # Nombre total de langues (pour calculer remise multi-langues)
    visibility: str = "public"  # "public" | "private" | "unlisted"


class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    progress_pct: int
    status_label: str
    error_msg: Optional[str] = None
    storage_url: Optional[str] = None
    storage_key: Optional[str] = None
    thumbnail_url: Optional[str] = None
    summary: Optional[str] = None
    summaries: Optional[dict] = None
    source_lang: Optional[str] = None
    target_lang: Optional[str] = None
    duration_s: Optional[float] = None
    video_type: Optional[str] = None
    can_download: bool = False
    is_public: bool = True
    estimated_total_seconds: Optional[float] = None
    estimated_burn_seconds: Optional[float] = None
    queue_position: Optional[int] = None
    estimated_start_in_s: Optional[float] = None
    source_url: Optional[str] = None
    video_width: Optional[int] = None
    video_height: Optional[int] = None
    source_storage_url: Optional[str] = None
    source_sub_url: Optional[str] = None
    vtt_url: Optional[str] = None
    vtt_source_url: Optional[str] = None
    original_filename: Optional[str] = None
    download_only: Optional[bool] = None
    mode: Optional[str] = None
    title: Optional[str] = None
    user_id: Optional[str] = None
    download_count: Optional[int] = None
    retry_count: Optional[int] = None
    job_metrics: Optional[dict] = None
    seo_slug: Optional[str] = None
    seo_metadata: Optional[dict] = None
    burned_languages: Optional[dict] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    archived_at: Optional[str] = None


class UpdateSegmentRequest(BaseModel):
    translation: str
    start_time: float
    end_time: float


class BurnRequest(BaseModel):
    user_id: Optional[str] = None


class ReorderRequest(BaseModel):
    segment_id: str
    new_order: int


class ExportClipsRequest(BaseModel):
    segment_ids: list[str] = []
    custom_clips: list[dict] = []  # [{"start_s": float, "end_s": float}]
    format: str = "16:9"
    concat: bool = True


class EstimateUrlRequest(BaseModel):
    source_url: str


class SplitSegmentRequest(BaseModel):
    split_time: float


class FeedbackRequest(BaseModel):
    rating: int
    issues: list[str] = []
    comment: str = ""


class MergeSegmentsRequest(BaseModel):
    segment_ids: list[str]