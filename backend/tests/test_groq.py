"""Tests for core/pipeline/groq.py — structured JSON output helpers."""

from __future__ import annotations

from core.pipeline.groq import (
    _whisper_segment_to_dict,
    _build_segments_list,
    _compute_timeout,
)


# ═══════════════════════════════════════════════════════════
#  _whisper_segment_to_dict
# ═══════════════════════════════════════════════════════════


class TestWhisperSegmentToDict:
    def test_basic_segment(self):
        """A normal Whisper segment produces the expected dict."""
        seg = {
            "start": 10.5,
            "end": 12.3,
            "text": " Hello world ",
            "avg_logprob": -0.45,
            "no_speech_prob": 0.02,
            "compression_ratio": 1.12,
            "tokens": [101, 2056, 2345],
            "temperature": 0.0,
        }
        result = _whisper_segment_to_dict(seg)
        assert result["start_s"] == 10.5
        assert result["end_s"] == 12.3
        assert result["text"] == "Hello world"
        assert result["confidence"] == -0.45
        assert result["no_speech_prob"] == 0.02
        assert result["compression_ratio"] == 1.12
        assert result["tokens"] == [101, 2056, 2345]
        assert result["temperature"] == 0.0

    def test_with_offset(self):
        """Offset is added to start and end times."""
        seg = {"start": 5.0, "end": 7.5, "text": "offset test"}
        result = _whisper_segment_to_dict(seg, offset_s=600.0)
        assert result["start_s"] == 605.0
        assert result["end_s"] == 607.5
        assert result["text"] == "offset test"

    def test_missing_fields(self):
        """Missing fields get sensible defaults."""
        result = _whisper_segment_to_dict({})
        assert result["start_s"] == 0.0
        assert result["end_s"] == 2.0
        assert result["text"] == ""
        assert result["confidence"] == 0.0
        assert result["no_speech_prob"] == 0.0
        assert result["compression_ratio"] == 1.0
        assert result["tokens"] == []
        assert result["temperature"] == 0.0

    def test_rounding_precision(self):
        """Values are rounded to the expected decimal places."""
        seg = {
            "start": 10.123456,
            "end": 12.654321,
            "text": "precision",
            "avg_logprob": -0.12345,
            "no_speech_prob": 0.123456,
        }
        result = _whisper_segment_to_dict(seg)
        assert result["start_s"] == 10.123  # 3dp
        assert result["end_s"] == 12.654  # 3dp
        assert result["confidence"] == -0.1235  # 4dp
        assert result["no_speech_prob"] == 0.1235  # 4dp

    def test_none_values_in_segment(self):
        """None values in numeric fields with 'or 0' fallback are handled.

        Note: start/end/text/temperature are NOT guarded by 'or 0' in the
        source code, but avg_logprob/no_speech_prob/compression_ratio are.
        """
        seg = {
            "start": 1.0,
            "end": 3.0,
            "text": "  hello  ",
            "avg_logprob": None,
            "no_speech_prob": None,
            "compression_ratio": None,
            "tokens": None,
            "temperature": 0.0,
        }
        result = _whisper_segment_to_dict(seg)
        assert result["start_s"] == 1.0
        assert result["end_s"] == 3.0
        assert result["text"] == "hello"
        # These use the "or 0" / "or 1" pattern, so None → default
        assert result["confidence"] == 0.0
        assert result["no_speech_prob"] == 0.0
        assert result["compression_ratio"] == 1.0
        assert result["tokens"] is None
        assert result["temperature"] == 0.0

    def test_text_gets_stripped(self):
        """Segment text is stripped of leading/trailing whitespace."""
        seg = {"start": 0.0, "end": 1.0, "text": "  \n  spaced  \n  "}
        result = _whisper_segment_to_dict(seg)
        assert result["text"] == "spaced"


# ═══════════════════════════════════════════════════════════
#  _build_segments_list
# ═══════════════════════════════════════════════════════════


class TestBuildSegmentsList:
    def test_empty_list(self):
        """An empty list of raw segments produces an empty result."""
        assert _build_segments_list([], "en") == []

    def test_single_segment(self):
        """A single segment is indexed and tagged with language."""
        raw = [{"start": 0.0, "end": 2.5, "text": "hello"}]
        result = _build_segments_list(raw, "fr")
        assert len(result) == 1
        assert result[0]["index"] == 1
        assert result[0]["language"] == "fr"
        assert result[0]["text"] == "hello"

    def test_multiple_segments_indexed(self):
        """Multiple segments get sequential indices starting at 1."""
        raw = [
            {"start": 0.0, "end": 1.0, "text": "first"},
            {"start": 1.0, "end": 2.0, "text": "second"},
            {"start": 2.0, "end": 3.0, "text": "third"},
        ]
        result = _build_segments_list(raw, "en")
        assert len(result) == 3
        assert [s["index"] for s in result] == [1, 2, 3]

    def test_filters_empty_text(self):
        """Segments with empty (or whitespace-only) text are filtered out."""
        raw = [
            {"start": 0.0, "end": 1.0, "text": "valid"},
            {"start": 1.0, "end": 2.0, "text": ""},
            {"start": 2.0, "end": 3.0, "text": "   "},
        ]
        result = _build_segments_list(raw, "en")
        assert len(result) == 1
        assert result[0]["text"] == "valid"
        assert result[0]["index"] == 1

    def test_offset_applied_to_all(self):
        """Offset is passed through to _whisper_segment_to_dict for every segment."""
        raw = [
            {"start": 0.0, "end": 1.0, "text": "A"},
            {"start": 1.0, "end": 2.0, "text": "B"},
        ]
        result = _build_segments_list(raw, "en", offset_s=300.0)
        assert result[0]["start_s"] == 300.0
        assert result[0]["end_s"] == 301.0
        assert result[1]["start_s"] == 301.0
        assert result[1]["end_s"] == 302.0

    def test_all_empty_filtered(self):
        """If all segments have empty text, result is an empty list."""
        raw = [
            {"start": 0.0, "end": 1.0, "text": ""},
            {"start": 1.0, "end": 2.0, "text": "  "},
        ]
        assert _build_segments_list(raw, "en") == []


# ═══════════════════════════════════════════════════════════
#  _compute_timeout
# ═══════════════════════════════════════════════════════════


class TestComputeTimeout:
    def test_short_audio(self):
        """Very short audio gets the minimum timeout (120s)."""
        assert _compute_timeout(1.0) == 120.0

    def test_medium_audio(self):
        """Audio of moderate duration produces computed timeout."""
        # 30 + (45 * 2) = 120
        assert _compute_timeout(45.0) == 120.0

    def test_long_audio(self):
        """Longer audio scales timeout linearly."""
        # 30 + (100 * 2) = 230
        assert _compute_timeout(100.0) == 230.0

    def test_maximum_capped(self):
        """Timeout is capped at 600s."""
        # 30 + (400 * 2) = 830, capped to 600
        assert _compute_timeout(400.0) == 600.0

    def test_boundary_at_max(self):
        """At exactly 285s audio, raw = 30+570 = 600, no cap needed."""
        assert _compute_timeout(285.0) == 600.0

    def test_boundary_at_min(self):
        """At exactly 45s audio, raw = 30+90 = 120, equal to min."""
        assert _compute_timeout(45.0) == 120.0

    def test_zero_audio(self):
        """Zero-duration audio still returns the min timeout."""
        assert _compute_timeout(0.0) == 120.0

    def test_negative_duration(self):
        """A negative duration (shouldn't happen) is clamped to min."""
        assert _compute_timeout(-10.0) == 120.0
