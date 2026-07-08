"""Tests for core/pipeline/watermark.py — sporadic watermark generation & bounds."""

from __future__ import annotations


from core.pipeline.watermark import (
    _generate_watermark_png,
    _get_watermark_bounds,
    _compute_sporadic_timecodes,
    _build_sporadic_drawtext_filters,
)


class TestGenerateWatermarkPng:
    """_generate_watermark_png est obsolete — retourne toujours None."""

    def test_returns_none(self):
        result = _generate_watermark_png(1280, 720)
        assert result is None, "PNG generation is obsolete"

    def test_with_text_returns_none(self):
        result = _generate_watermark_png(1280, 720, text="Custom")
        assert result is None

    def test_with_mode_returns_none(self):
        result = _generate_watermark_png(1280, 720, mode="sporadic")
        assert result is None

    def test_any_resolution_returns_none(self):
        for w, h in [(640, 360), (1920, 1080), (480, 480)]:
            result = _generate_watermark_png(w, h)
            assert result is None, f"Should return None for {w}x{h}"


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


class TestSporadicTimecodes:
    """Tests for _compute_sporadic_timecodes."""

    def test_returns_list_of_tuples(self):
        timecodes = _compute_sporadic_timecodes(120.0)
        assert isinstance(timecodes, list)
        assert len(timecodes) > 0
        for start, end in timecodes:
            assert isinstance(start, float)
            assert isinstance(end, float)
            assert start < end

    def test_starts_at_zero_for_thumbnail(self):
        timecodes = _compute_sporadic_timecodes(120.0)
        first_start = timecodes[0][0]
        assert first_start == 0.0, "First watermark at t=0 for thumbnails"

    def test_respects_duration(self):
        timecodes = _compute_sporadic_timecodes(30.0, interval=15, text_duration=4)
        for start, end in timecodes:
            assert end <= 30.0


class TestSporadicDrawtextFilters:
    """Tests for _build_sporadic_drawtext_filters."""

    def test_empty_input_returns_empty(self):
        chain, label = _build_sporadic_drawtext_filters(
            1280, 720, "", [], opacity=0.6
        )
        assert chain == ""
        assert label == "base"

    def test_no_timecodes_returns_empty(self):
        chain, label = _build_sporadic_drawtext_filters(
            1280, 720, "Hello", [], opacity=0.6
        )
        assert chain == ""

    def test_returns_filter_string(self):
        timecodes = [(5.0, 9.0)]
        chain, label = _build_sporadic_drawtext_filters(
            1280, 720, "Hello", timecodes, opacity=0.6
        )
        assert "drawtext" in chain
        assert "text='Hello'" in chain or "text='Hello" in chain
        assert label == "s0"

    def test_multiple_timecodes(self):
        timecodes = [(5.0, 9.0), (20.0, 24.0)]
        chain, label = _build_sporadic_drawtext_filters(
            1280, 720, "Test", timecodes, opacity=0.6
        )
        assert "s0" in chain
        assert "s1" in chain
        assert label == "s1"
