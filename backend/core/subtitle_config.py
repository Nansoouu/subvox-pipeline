"""
subtitle_config.py — Pont vers l'implémentation réelle (subvox-confidential).

Ce fichier tente d'importer et ré-exporter le module confidentiel.
Si indisponible, fournit un stub minimal pour éviter les crashs.
"""

import importlib
import logging
import os as _os
import sys as _sys

logger = logging.getLogger(__name__)

# ── Tentative de chargement du module confidentiel ─────────────────────
_conf_backend = _os.path.join(
    _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),
    "..", "..", "subvox-confidential", "backend"
)
_conf_core = _os.path.join(_conf_backend, "core")
_conf_file = _os.path.join(_conf_core, "subtitle_config.py")

_has_real = False
if _os.path.exists(_conf_file):
    try:
        # Injecter le path dans sys.path pour l'import
        if _conf_backend not in _sys.path:
            _sys.path.insert(0, _conf_backend)

        # Importer le module réel
        spec = importlib.util.spec_from_file_location(
            "core.subtitle_config_real", _conf_file
        )
        if spec and spec.loader:
            real_mod = importlib.util.module_from_spec(spec)
            # Simuler le namespace core.subtitle_config pour que les imports internes marchent
            _sys.modules["core.subtitle_config_real"] = real_mod
            spec.loader.exec_module(real_mod)

            # Ré-exporter tout ce que le module réel exporte
            for attr in dir(real_mod):
                if not attr.startswith("_"):
                    globals()[attr] = getattr(real_mod, attr)

            _has_real = True
            logger.debug("subtitle_config: loaded real implementation from subvox-confidential")
    except Exception as e:
        logger.warning(f"subtitle_config: failed to load confidential module: {e}")

# ── Stub de secours (si pas de module confidentiel) ────────────────────
if not _has_real:

    class SubtitleConfig:
        """Stub — true implementation lives in subvox-confidential."""

        defaults: dict = {"default_font_size": 18, "default_opacity": 100}
        is_vertical: bool = False

        def __init__(self, *args, **kwargs):
            pass

        def calculate_font_size(self) -> int:
            return 18

        def calculate_max_chars_per_line(self) -> int:
            return 40

        def calculate_margins(self) -> tuple:
            return (20, 20, 20)

        def to_ass_style(self) -> str:
            return "*Default,Arial,18,&H00FFFFFF,&H000000FF,&H00000000,&H64000000,0,0,0,0,100,100,0,0,1,1,1,2,20,20,20,1"

        def get(self, key: str, default=None):
            return self.defaults.get(key, default)

        def get_watermark_safe_zone(self) -> tuple[float, float]:
            """Return top-fraction and bottom-fraction of the watermark safe zone."""
            return (0.0, 0.2)

        def get_watermark_max_dims(self) -> tuple[int, int]:
            """Return max (width, height) in pixels for watermark."""
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

    async def upload_video(*args, **kwargs):
        return None

    async def upload_text(*args, **kwargs):
        return None

    def load_user_style_from_json(*args, **kwargs):
        return None

    logger.debug("subtitle_config: using public stub (subvox-confidential not available)")
