"""email.py — Placeholder. Full implementation in subvox-confidential."""

import logging
logger = logging.getLogger(__name__)

logger.debug("Using public email stub — business features from subvox-confidential are inactive")

# Stub functions
async def check_quota(*args, **kwargs): return True, ""
def record_usage(*args, **kwargs): pass
async def send_confirmation_email(*args, **kwargs): return True
async def upload_video(*args, **kwargs): return None
async def upload_text(*args, **kwargs): return None
class SubtitleConfig:
    def __init__(self, *args, **kwargs): pass
def load_user_style_from_json(*args, **kwargs): return None
