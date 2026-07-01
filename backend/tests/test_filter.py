"""Tests for core/pipeline/steps/filter.py — structured JSON filter logic."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.pipeline.steps.filter import _build_srt_from_segments


# ═══════════════════════════════════════════════════════════
#  _build_srt_from_segments
# ═══════════════════════════════════════════════════════════


class TestBuildSrtFromSegments:
    def test_single_segment(self):
        """A single segment produces a valid SRT block."""
        segments = [
            {
                "index": 1,
                "start_s": 0.0,
                "end_s": 2.5,
                "text": "Hello world",
            }
        ]
        expected = "1\n00:00:00,000 --> 00:00:02,500\nHello world\n"
        assert _build_srt_from_segments(segments) == expected

    def test_multiple_segments(self):
        """Multiple segments produce multiple SRT blocks separated by newlines."""
        segments = [
            {"index": 1, "start_s": 0.0, "end_s": 1.0, "text": "First"},
            {"index": 2, "start_s": 1.5, "end_s": 3.0, "text": "Second"},
        ]
        expected = (
            "1\n00:00:00,000 --> 00:00:01,000\nFirst\n"
            "\n"
            "2\n00:00:01,500 --> 00:00:03,000\nSecond\n"
        )
        assert _build_srt_from_segments(segments) == expected

    def test_empty_list(self):
        """An empty segment list produces an empty string."""
        assert _build_srt_from_segments([]) == ""

    def test_skips_empty_text(self):
        """Segments with missing or whitespace-only text are skipped."""
        segments = [
            {"index": 1, "start_s": 0.0, "end_s": 1.0, "text": "Keep"},
            {"index": 2, "start_s": 1.0, "end_s": 2.0, "text": ""},
            {"index": 3, "start_s": 2.0, "end_s": 3.0, "text": "   "},
        ]
        result = _build_srt_from_segments(segments)
        assert "Keep" in result
        # The empty-text segments should not produce SRT blocks
        assert "1\n00:00:00,000 --> 00:00:01,000\nKeep\n" in result
        assert "00:00:02,000 --> 00:00:03,000" not in result

    def test_missing_start_end_default(self):
        """Missing start_s/end_s use sensible defaults."""
        segments = [
            {"index": 5, "text": "default times"},
        ]
        result = _build_srt_from_segments(segments)
        assert "5\n00:00:00,000 --> 00:00:02,000\ndefault times\n" in result

    def test_missing_index_default(self):
        """Missing index defaults to 1."""
        segments = [
            {"start_s": 10.0, "end_s": 12.0, "text": "no index"},
        ]
        result = _build_srt_from_segments(segments)
        assert result.startswith("1\n")


# ═══════════════════════════════════════════════════════════
#  step_filter with segments_json
# ═══════════════════════════════════════════════════════════


class TestStepFilterWithSegmentsJson:
    """Test step_filter() using the structured segments_json path."""

    @pytest.fixture(autouse=True)
    def _patch_deps(self):
        """Mock whisper_hallucination_filter and _get_tmp for all tests.

        is_hallucination and apply_llm_hallucination_filter are imported
        inside step_filter() from core.whisper_hallucination_filter, so
        we patch at that module's source location.

        _get_tmp is configured so that tmp / "transcript.srt" does NOT
        exist (exists() -> False) to avoid interfering with srt_raw tests.
        """
        mock_tmp = MagicMock()
        mock_srt_path = MagicMock()
        mock_srt_path.exists.return_value = False
        mock_tmp.__truediv__.return_value = mock_srt_path
        with (
            patch(
                "core.whisper_hallucination_filter.is_hallucination",
                return_value=False,
            ) as mock_hallucination,
            patch(
                "core.whisper_hallucination_filter.apply_llm_hallucination_filter",
                AsyncMock(return_value=(0, 0)),
            ),
            patch(
                "core.pipeline.steps.filter._get_tmp",
                return_value=mock_tmp,
            ),
        ):
            self.mock_is_hallucination = mock_hallucination
            yield

    @pytest.fixture
    def sample_segments(self):
        return [
            {
                "index": 1,
                "start_s": 0.0,
                "end_s": 2.5,
                "text": "Hello and welcome to this video",
                "confidence": -0.3,
                "no_speech_prob": 0.01,
                "language": "en",
            },
            {
                "index": 2,
                "start_s": 2.5,
                "end_s": 5.0,
                "text": "Today we will discuss important topics",
                "confidence": -0.5,
                "no_speech_prob": 0.02,
                "language": "en",
            },
            {
                "index": 3,
                "start_s": 5.0,
                "end_s": 7.0,
                "text": "Thank you for watching",
                "confidence": -0.2,
                "no_speech_prob": 0.01,
                "language": "en",
            },
        ]

    async def _run_filter(self, segments, srt_raw=""):
        """Helper: import and call step_filter."""
        from core.pipeline.steps.filter import step_filter

        result = await step_filter(
            job_id="test-job",
            srt_raw=srt_raw,
            segments_json=segments,
        )
        return result

    # ── Normal pass-through ─────────────────────────────────

    async def test_normal_segments_pass_through(self, sample_segments):
        """Normal segments pass through without being removed."""
        result = await self._run_filter(sample_segments)
        data = result.data
        assert data["total_input"] == 3
        assert data["total_output"] == 3
        assert data["removed_regex"] == 0
        assert len(data["segments"]) == 3

    async def test_output_has_correct_keys(self, sample_segments):
        """The output dict contains all expected keys."""
        result = await self._run_filter(sample_segments)
        data = result.data
        assert "raw_srt" in data
        assert "segments" in data
        assert "removed_regex" in data
        assert "removed_llm" in data
        assert "total_input" in data
        assert "total_output" in data
        assert "avg_confidence" in data

    async def test_avg_confidence_computed(self, sample_segments):
        """Average confidence of kept segments is computed correctly."""
        result = await self._run_filter(sample_segments)
        # (-0.3 + -0.5 + -0.2) / 3 = -0.3333
        assert result.data["avg_confidence"] == pytest.approx(-0.3333, abs=0.001)

    async def test_raw_srt_produced(self, sample_segments):
        """raw_srt is a valid SRT string built from segments."""
        result = await self._run_filter(sample_segments)
        assert result.data["raw_srt"].startswith("1\n")
        assert "Hello and welcome" in result.data["raw_srt"]

    # ── Confidence filter ───────────────────────────────────

    async def test_low_confidence_short_text_removed(self):
        """Segments with low confidence + short text are filtered out."""
        segments = [
            {
                "index": 1,
                "start_s": 0.0,
                "end_s": 1.0,
                "text": "hi",  # <= 3 words
                "confidence": -1.5,  # < -1.0
                "no_speech_prob": 0.01,
                "language": "en",
            },
            {
                "index": 2,
                "start_s": 1.0,
                "end_s": 3.0,
                "text": "Good morning everyone",
                "confidence": -0.3,
                "no_speech_prob": 0.01,
                "language": "en",
            },
        ]
        result = await self._run_filter(segments)
        assert result.data["total_input"] == 2
        assert result.data["total_output"] == 1
        assert result.data["removed_regex"] == 1
        # The kept segment (Good morning everyone) should have no filter_reason
        assert result.data["segments"][0]["filter_reason"] == ""
        assert result.data["segments"][0]["text"] == "Good morning everyone"

    async def test_low_confidence_but_long_text_kept(self):
        """Even with low confidence, long text (>= 4 words) is kept."""
        segments = [
            {
                "index": 1,
                "start_s": 0.0,
                "end_s": 3.0,
                "text": "This is a longer phrase",
                "confidence": -1.5,  # < -1.0 but 4 words > 3
                "no_speech_prob": 0.01,
                "language": "en",
            },
        ]
        result = await self._run_filter(segments)
        assert result.data["total_output"] == 1
        assert result.data["removed_regex"] == 0

    # ── No_speech filter ────────────────────────────────────

    async def test_high_no_speech_short_text_removed(self):
        """Segments with high no_speech_prob + short text are filtered out."""
        segments = [
            {
                "index": 1,
                "start_s": 0.0,
                "end_s": 1.0,
                "text": "ok",  # <= 2 words
                "confidence": -0.3,
                "no_speech_prob": 0.9,  # > 0.8
                "language": "en",
            },
            {
                "index": 2,
                "start_s": 1.0,
                "end_s": 3.0,
                "text": "Real content here",
                "confidence": -0.3,
                "no_speech_prob": 0.01,
                "language": "en",
            },
        ]
        result = await self._run_filter(segments)
        assert result.data["total_output"] == 1
        assert result.data["removed_regex"] == 1
        # The kept segment (Real content here) should have no filter_reason
        assert result.data["segments"][0]["filter_reason"] == ""
        assert result.data["segments"][0]["text"] == "Real content here"

    async def test_high_no_speech_but_long_text_kept(self):
        """Even with high no_speech_prob, longer text (>= 3 words) is kept."""
        segments = [
            {
                "index": 1,
                "start_s": 0.0,
                "end_s": 3.0,
                "text": "three words now",
                "confidence": -0.3,
                "no_speech_prob": 0.9,  # > 0.8 but 3 words > 2
                "language": "en",
            },
        ]
        result = await self._run_filter(segments)
        assert result.data["total_output"] == 1
        assert result.data["removed_regex"] == 0

    # ── Hallucination regex filter (via mock) ───────────────

    async def test_hallucination_removed(self, sample_segments):
        """Segments flagged by is_hallucination() are removed."""
        # Make the second segment look like a hallucination
        async def _with_hallucination_second():
            # We'll patch per-call by setting side_effect
            pass

        self.mock_is_hallucination.side_effect = [False, True, False]
        result = await self._run_filter(sample_segments)
        assert result.data["total_output"] == 2
        assert result.data["removed_regex"] == 1
        assert result.data["segments"][0]["text"] == "Hello and welcome to this video"
        assert result.data["segments"][1]["text"] == "Thank you for watching"

    # ── All-filtered guard ──────────────────────────────────

    async def test_all_filtered_guard_keeps_original(self):
        """If segments_json is provided but everything is filtered, keep original."""
        segments = [
            {
                "index": 1,
                "start_s": 0.0,
                "end_s": 1.0,
                "text": "hi",
                "confidence": -2.0,
                "no_speech_prob": 0.01,
                "language": "en",
            },
        ]
        # This segment has low confidence and <=3 words, so it gets filtered
        # Since there's no srt_raw, the guard checks srt_raw...
        # Actually let's test the case where srt_raw is empty and all filtered
        result = await self._run_filter(segments, srt_raw="")
        # Without srt_raw, the guard condition (not filtered_segments and srt_raw)
        # is false, so we get 0 output
        assert result.data["total_output"] == 0
        assert result.data["removed_regex"] == 1

    async def test_all_filtered_guard_with_srt_raw(self):
        """If all filtered but srt_raw exists, guard keeps original segments."""
        segments = [
            {
                "index": 1,
                "start_s": 0.0,
                "end_s": 1.0,
                "text": "hi",
                "confidence": -2.0,
                "no_speech_prob": 0.01,
                "language": "en",
            },
        ]
        result = await self._run_filter(
            segments,
            srt_raw="1\n00:00:00,000 --> 00:00:01,000\nhi\n",
        )
        # Guard fires: all filtered but srt_raw exists → keeps original
        assert result.data["total_output"] == 1
        assert result.data["removed_regex"] == 0
        assert result.data["segments"][0]["text"] == "hi"

    # ── Empty segments input ────────────────────────────────

    async def test_empty_segments_list(self):
        """An empty segments_json list produces zero output."""
        result = await self._run_filter([], srt_raw="")
        assert result.data["total_input"] == 0
        assert result.data["total_output"] == 0
        assert result.data["removed_regex"] == 0
        assert result.data["avg_confidence"] == 0.0

    async def test_empty_text_removed(self):
        """Segments with empty text are removed as regex removals."""
        segments = [
            {
                "index": 1,
                "start_s": 0.0,
                "end_s": 1.0,
                "text": "",
                "confidence": 0.0,
                "no_speech_prob": 0.0,
                "language": "en",
            },
        ]
        result = await self._run_filter(segments)
        assert result.data["total_input"] == 1
        assert result.data["total_output"] == 0
        assert result.data["removed_regex"] == 1
