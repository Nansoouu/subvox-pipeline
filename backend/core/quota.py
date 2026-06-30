"""quota.py — Placeholder. Full quota tracking in subvox-confidential."""

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

GROQ_FREE_POOL_DAILY_S = 1800
GROQ_DAILY_LIMIT_S = 600


@dataclass
class QuotaCheck:
    allowed: bool = True
    status_code: int = 200
    detail: str = ""
    remaining_s: int = GROQ_DAILY_LIMIT_S
    plan: str = "public"


@dataclass
class QuotaInfo:
    role: str = "user"
    max_duration_s: int = 3600
    daily_limit: int = 100
    daily_used: int = 0
    daily_remaining: int = 100
    watermark_forced: bool = False
    has_groq_key: bool = False
    groq_key_valid: bool = False
    groq_daily_limit_s: int = 600
    groq_daily_used_s: int = 0
    groq_status: str = "ok"
    plan: str = "free"


async def get_user_quota(user_id: str) -> QuotaInfo:
    return QuotaInfo()


async def get_free_pool_remaining_s():
    return GROQ_FREE_POOL_DAILY_S


async def check_quota(user, request=None, duration_s=0) -> QuotaCheck:
    """Always passes in public mode."""
    return QuotaCheck()


async def record_usage(user, job_id: str, duration_s: float):
    """Forward to confidential quota if available."""
    try:
        import sys as _sys, os as _os
        _conf = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "..", "subvox-confidential", "backend")
        if _conf not in _sys.path:
            _sys.path.insert(0, _conf)
        from core.quota import record_usage as _real
        await _real(user, job_id, duration_s)
    except Exception:
        pass  # Dev mode sans confidential — skip


async def get_quota_status(user_id: str) -> dict:
    return {"can_process": True, "remaining_s": GROQ_DAILY_LIMIT_S, "plan": "public"}
