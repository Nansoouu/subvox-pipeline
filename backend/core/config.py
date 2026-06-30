"""core/config.py — Configuration centralisée — Subvox

Charge la configuration depuis config.yaml (prioritaire) ou les variables d'environnement.
Ne dépend PAS de .env — tout est dans un seul fichier YAML.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import yaml


def _load_yaml_config() -> dict:
    """Charge config.yaml à la racine du projet."""
    config_path = Path(__file__).resolve().parent.parent.parent / "config.yaml"
    if config_path.exists():
        with open(config_path) as f:
            return yaml.safe_load(f) or {}
    return {}


_yaml = _load_yaml_config()


def _get(key: str, default: str = "") -> str:
    """Récupère une valeur : YAML > env var > default."""
    env_key = key.upper()
    yaml_val = _yaml.get(key)
    if yaml_val is not None and yaml_val != "":
        return str(yaml_val)
    env_val = os.getenv(env_key)
    if env_val is not None:
        return env_val
    return default


def _get_bool(key: str, default: bool = False) -> bool:
    val = _get(key, str(default)).lower()
    return val in ("true", "1", "yes", "on")


def _get_int(key: str, default: int = 0) -> int:
    try:
        return int(_get(key, str(default)))
    except ValueError:
        return default


def _get_float(key: str, default: float = 0.0) -> float:
    try:
        return float(_get(key, str(default)))
    except ValueError:
        return default


class Settings:
    """Configuration Subvox — interface compatible avec l'ancien BaseSettings."""

    # ── PostgreSQL ───────────────────────────────────────────────────
    DATABASE_URL: str = _get("database_url", "postgresql://localhost:5432/subvox")
    DATABASE_URL_POOLER: Optional[str] = _get("database_url_pooler") or None
    DB_POOL_MIN: int = _get_int("db_pool_min", 2)
    DB_POOL_MAX: int = _get_int("db_pool_max", 10)

    # ── Redis ────────────────────────────────────────────────────────
    REDIS_URL: str = _get("redis_url", "redis://localhost:6379/0")

    # ── SUBVOX Token Economy ───────────────────────────────────────────
    SUBVOX_HOLDER_MIN_BALANCE: int = 500_000
    SUBVOX_SPLIT_PROVIDER: float = 0.75
    SUBVOX_SPLIT_PLATFORM: float = 0.15
    SUBVOX_SPLIT_HOLDERS: float = 0.10

    # ── URLs ─────────────────────────────────────────────────────────
    FRONTEND_URL: str = _get("frontend_url", "http://localhost:3000")

    # ── JWT ──────────────────────────────────────────────────────────
    JWT_SECRET: str = _get("jwt_secret", "change-me-in-production")
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION_HOURS: int = 24

    # ── Supabase (optionnel) ──────────────────────────────────────────
    SUPABASE_URL: Optional[str] = _get("supabase_url") or None
    SUPABASE_SERVICE_KEY: Optional[str] = _get("supabase_service_key") or None
    SUPABASE_BUCKET: str = _get("supabase_bucket", "translated-videos")

    # ── Sentry (optionnel) ────────────────────────────────────────────
    SENTRY_DSN: Optional[str] = _get("sentry_dsn") or None
    ENVIRONMENT: str = _get("environment", "development")
    APP_ENV: str = _get("app_env", "development")

    # ── Resend emails (optionnel) ─────────────────────────────────────
    RESEND_API_KEY: Optional[str] = _get("resend_api_key") or None
    RESEND_FROM_EMAIL: str = _get("resend_from_email", "noreply@subvox.dev")
    RESEND_FROM_NAME: str = "Subvox"

    # ── Groq ─────────────────────────────────────────────────────────
    GROQ_API_KEY: Optional[str] = _get("groq_api_key") or os.environ.get("GROQ_API_KEY") or None
    GROQ_POOL_PUBLIC: int = 45
    GROQ_ENCRYPTION_KEY: Optional[str] = None
    BOOTSTRAP_GROQ_KEYS: int = 3

    # ── DeepSeek ─────────────────────────────────────────────────
    DEEPSEEK_API_KEY: Optional[str] = _get("deepseek_api_key") or None

    # ── Ollama (local translation) ──────────────────────────────────────
    TRANSLATION_PROVIDER: str = _get("translation_provider", "deepseek")  # deepseek | ollama
    OLLAMA_URL: str = _get("ollama_url", "http://localhost:11434")
    OLLAMA_MODEL: str = _get("ollama_model", "qwen2.5:3b")
    OLLAMA_TIMEOUT: float = _get_float("ollama_timeout", 300.0)

    # ── CORS ─────────────────────────────────────────────────────────
    CORS_ORIGINS: str = _get("cors_origins", "http://localhost:3000,http://localhost:3001,http://localhost:3002")
    ECONOMY_URL: str = _get("economy_url", "http://localhost:8001")

    # ── Voicebox ─────────────────────────────────────────────────────
    VOICEBOX_API_URL: str = _get("voicebox_api_url", "http://voicebox:8000")

    # ── Pipeline ─────────────────────────────────────────────────────
    SOFT_SUBS_ENABLED: bool = _get_bool("soft_subs_enabled", False)
    LOCAL_TEMP_DIR: str = _get("local_temp_dir", "/tmp/subvox-processing")
    ANONYMIZE_ENABLED: bool = _get_bool("anonymize_enabled", True)
    VISUAL_ANALYSIS_INTERVAL_BASE: int = 5
    ANALYSIS_WORKER_QUEUE: str = "video_analysis"
    VIDEO_SHORT_MAX_SECONDS: int = 120
    VIDEO_MAX_SECONDS: int = _get_int("max_video_duration_s", 5400)
    WATERMARK_TEXT: str = _get("watermark_text", "Subtitled by Subvox")
    WATERMARK_LOGO_PATH: str = ""
    WATERMARK_MODE: str = "fixed_text"
    WATERMARK_POSITION: str = "top-right"
    WATERMARK_OPACITY: float = 1.0
    WATERMARK_SPORADIC_ENABLED: bool = True
    WATERMARK_SPORADIC_INTERVAL: float = 8
    WATERMARK_SPORADIC_DURATION: float = 8
    WATERMARK_SPORADIC_OPACITY: float = 0.6

    # ── Quotas ───────────────────────────────────────────────────────
    FREE_DAILY_VIDEOS: int = 3
    FREE_MAX_MINUTES: int = 2
    PRO_MAX_MINUTES: int = 15
    MASTER_DAILY_MINUTES: int = 90

    # ── Logging ──────────────────────────────────────────────────────
    LOG_LEVEL: str = _get("log_level", "INFO")
    LOG_FORMAT: str = "json"
    LOG_FILE: str | None = None


settings = Settings()
