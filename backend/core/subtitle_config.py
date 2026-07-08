"""
subtitle_config.py — Configuration intelligente des sous-titres (ASS).
Délégue au module confidentiel si disponible, sinon utilise un stub.

Le module confidentiel (subvox-confidential/subtitle_config.py) est chargé
uniquement s'il existe dans le PYTHONPATH.
"""

from __future__ import annotations

import logging as _logging

logger = _logging.getLogger(__name__)

_has_real = False
try:
    from subtitle_config import SubtitleConfig as _RealSubtitleConfig
    from subtitle_config import check_quota, record_usage, send_confirmation_email

    _has_real = True
    logger.info("subtitle_config: using real module (subvox-confidential)")
except ImportError:
    logger.info("subtitle_config: confidential module not found, using stub")

# ── Stub de secours (si pas de module confidentiel) ────────────────────
if not _has_real:

    class SubtitleConfig:
        """Stub — true implementation lives in subvox-confidential."""

        defaults: dict = {"default_font_size": 18, "default_opacity": 100}
        is_vertical: bool = False
        _vid_w: int = 1280
        _vid_h: int = 720

        def __init__(self, *args, **kwargs):
            if args:
                self._vid_w = args[0] if len(args) > 0 else 1280
                self._vid_h = args[1] if len(args) > 1 else 720
            elif kwargs:
                self._vid_w = kwargs.get("vid_w", 1280)
                self._vid_h = kwargs.get("vid_h", 720)
            self._font_size = max(28, min(64, int(self._vid_h * 0.045)))
            self.defaults["default_font_size"] = self._font_size

        def calculate_font_size(self) -> int:
            return self._font_size

        def calculate_max_chars_per_line(self) -> int:
            return max(20, min(60, int(self._vid_w / 24)))

        def calculate_margins(self) -> tuple:
            mlr = max(16, int(self._vid_w * 0.02))
            mv = max(24, int(self._vid_h * 0.08))
            return (mlr, mlr, mv)

        def to_ass_style(self) -> str:
            mlr, _, mv = self.calculate_margins()
            return f"Style: Default,Arial,{self._font_size},&H00FFFFFF,&H000000FF,&H00000000,&HFF000000,-1,0,0,0,100,100,0,0,3,2,0,2,{mlr},{mlr},{mv},1"

        def get(self, key: str, default=None):
            return self.defaults.get(key, default)

        def get_watermark_safe_zone(self) -> tuple[float, float]:
            return (0.0, 0.2)

        def get_watermark_max_dims(self) -> tuple[int, int]:
            return (300, 100)

        def __getattr__(self, name):
            if name == "defaults":
                return self.defaults
            raise AttributeError(f"'SubtitleConfig' object has no attribute '{name}'")

    async def check_quota(*args, **kwargs):
        return True, ""

    def record_usage(*args, **kwargs):
        pass

    async def send_confirmation_email(*args, **kwargs):
        return True


def load_user_style_from_json(json_str: str) -> dict | None:
    """Stub — parse un JSON en dict, retourne None si invalide."""
    import json as _json
    try:
        return _json.loads(json_str)
    except Exception:
        return None
