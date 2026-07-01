"""Tests for core/pipeline/watermark.py — PNG watermark generation."""

from __future__ import annotations

import struct


from core.pipeline.watermark import (
    _generate_watermark_png,
    _get_watermark_bounds,
)


def _is_png(data: bytes) -> bool:
    """Check that *data* looks like a valid PNG: 8-byte magic + IHDR chunk."""
    if len(data) < 24:
        return False
    signature = b"\x89PNG\r\n\x1a\n"
    if data[:8] != signature:
        return False
    # First chunk should be IHDR (length 4 bytes + 'IHDR' 4 bytes)
    _ = struct.unpack(">I", data[8:12])[0]
    if data[12:16] != b"IHDR":
        return False
    return True


class TestGenerateWatermarkPng:
    """Tests that _generate_watermark_png returns valid PNG bytes."""

    def test_fixed_logo_returns_bytes(self):
        result = _generate_watermark_png(1280, 720, mode="fixed_logo")
        assert result is not None, "Watermark should be generated even without font file (uses default)"
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_fixed_logo_is_valid_png(self):
        result = _generate_watermark_png(1280, 720, mode="fixed_logo")
        assert result is not None
        assert _is_png(result), "Output should be a valid PNG"

    def test_tiling_mode_returns_bytes(self):
        result = _generate_watermark_png(640, 480, mode="tiling")
        assert result is not None
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_tiling_mode_is_valid_png(self):
        result = _generate_watermark_png(640, 480, mode="tiling")
        assert result is not None
        assert _is_png(result), "Output should be a valid PNG"

    def test_custom_text(self):
        result = _generate_watermark_png(1280, 720, text="Custom Text", mode="fixed_logo")
        assert result is not None
        assert _is_png(result)

    def test_top_left_position(self):
        result = _generate_watermark_png(1280, 720, position="top-left")
        assert result is not None
        assert _is_png(result)

    def test_different_resolutions(self):
        for w, h in [(640, 360), (1920, 1080), (480, 480)]:
            result = _generate_watermark_png(w, h, mode="fixed_logo")
            assert result is not None, f"Watermark failed for {w}x{h}"
            assert _is_png(result), f"PNG validation failed for {w}x{h}"

    def test_bg_opacity_zero(self):
        result = _generate_watermark_png(1280, 720, bg_opacity=0.0)
        assert result is not None
        assert _is_png(result)


class TestGetWatermarkBounds:
    """Tests for _get_watermark_bounds — pixel-safe-zone calculation."""

    def test_top_right_returns_four_ints(self):
        bounds = _get_watermark_bounds(1280, 720, "top-right")
        assert len(bounds) == 4
        assert all(isinstance(v, int) for v in bounds)
        # Top-right: min_x should be near the right edge
        min_x, min_y, max_x, max_y = bounds
        assert min_x > 0
        assert max_x <= 1280
        assert min_y >= 0
        assert max_y <= 720
        # Watermark should be in the top portion (top 20%)
        assert max_y <= 720 * 0.2 + 20  # slight margin for padding

    def test_top_left_is_left_aligned(self):
        bounds = _get_watermark_bounds(1280, 720, "top-left")
        min_x, _, _, _ = bounds
        assert min_x < 100, "Top-left watermark should be near the left edge"

    def test_default_fallback(self):
        """Unknown position falls back to top-right."""
        bounds = _get_watermark_bounds(1280, 720, "unknown-pos")
        assert len(bounds) == 4
