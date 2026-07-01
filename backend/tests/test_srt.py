"""Tests for core/pipeline/srt.py — pure-function SRT/ASS helpers."""

from __future__ import annotations


from core.pipeline.srt import (
    _to_srt_time,
    _parse_time_to_seconds,
    _srt_time_to_ass,
    _parse_srt,
    _write_srt,
    _shift_srt_timing,
    _adjust_duration_based_on_text,
)

# ═══════════════════════════════════════════════════════════
#  _to_srt_time
# ═══════════════════════════════════════════════════════════


class TestToSrtTime:
    def test_zero(self):
        assert _to_srt_time(0.0) == "00:00:00,000"

    def test_whole_seconds(self):
        assert _to_srt_time(1.0) == "00:00:01,000"

    def test_one_hour_one_min_one_s(self):
        assert _to_srt_time(3661.5) == "01:01:01,500"

    def test_milliseconds_rounding(self):
        assert _to_srt_time(0.123) == "00:00:00,123"

    def test_large_value(self):
        # Floating-point: 0.999 * 1000 → 998 due to float precision
        assert _to_srt_time(86399.999) == "23:59:59,998"

    def test_negative_value(self):
        """_to_srt_time works modulo arithmetic on negative inputs."""
        assert _to_srt_time(-1.0) == "-1:59:59,000"


# ═══════════════════════════════════════════════════════════
#  _parse_time_to_seconds
# ═══════════════════════════════════════════════════════════


class TestParseTimeToSeconds:
    def test_basic(self):
        assert _parse_time_to_seconds("00:00:01,000") == 1.0

    def test_one_hour(self):
        assert _parse_time_to_seconds("01:01:01,500") == 3661.5

    def test_zero(self):
        assert _parse_time_to_seconds("00:00:00,000") == 0.0

    def test_milliseconds(self):
        assert _parse_time_to_seconds("00:00:00,050") == 0.050

    def test_trailing_spaces(self):
        assert _parse_time_to_seconds("  00:00:02,000  ") == 2.0


# ═══════════════════════════════════════════════════════════
#  _srt_time_to_ass
# ═══════════════════════════════════════════════════════════


class TestSrtTimeToAss:
    def test_basic(self):
        assert _srt_time_to_ass("00:00:01,000") == "0:00:01.00"

    def test_one_hour(self):
        assert _srt_time_to_ass("01:01:01,500") == "1:01:01.50"

    def test_centiseconds_rounding(self):
        # 123 ms → 12 cs
        assert _srt_time_to_ass("00:00:00,123") == "0:00:00.12"

    def test_leading_hour(self):
        assert _srt_time_to_ass("02:30:45,789") == "2:30:45.78"


# ═══════════════════════════════════════════════════════════
#  _parse_srt / _write_srt
# ═══════════════════════════════════════════════════════════


class TestParseSrt:
    SAMPLE = """1
00:00:01,000 --> 00:00:04,000
Hello world

2
00:00:05,000 --> 00:00:08,500
This is a subtitle
with two lines"""

    def test_parse_basic(self):
        blocks = _parse_srt(self.SAMPLE)
        assert len(blocks) == 2

        assert blocks[0]["index"] == "1"
        assert blocks[0]["timecode"] == "00:00:01,000 --> 00:00:04,000"
        assert blocks[0]["text"] == "Hello world"

        assert blocks[1]["index"] == "2"
        assert blocks[1]["timecode"] == "00:00:05,000 --> 00:00:08,500"
        assert blocks[1]["text"] == "This is a subtitle\nwith two lines"

    def test_parse_empty(self):
        assert _parse_srt("") == []

    def test_parse_whitespace_only(self):
        assert _parse_srt("   \n\n  ") == []

    def test_parse_single_block_no_text(self):
        # A block with only index+timecode (<3 lines) should be skipped
        blocks = _parse_srt("1\n00:00:01,000 --> 00:00:02,000")
        assert len(blocks) == 0


class TestWriteSrt:
    def test_write_single(self):
        blocks = [
            {
                "index": "1",
                "timecode": "00:00:01,000 --> 00:00:04,000",
                "text": "Hello world",
            }
        ]
        expected = "1\n00:00:01,000 --> 00:00:04,000\nHello world\n"
        assert _write_srt(blocks) == expected

    def test_roundtrip(self):
        """Parse → write → parse should round-trip cleanly."""
        original = """1
00:00:01,000 --> 00:00:04,000
Hello world

2
00:00:05,000 --> 00:00:08,500
Line one
Line two"""
        blocks = _parse_srt(original)
        rebuilt = _write_srt(blocks)
        blocks2 = _parse_srt(rebuilt)
        assert blocks == blocks2


# ═══════════════════════════════════════════════════════════
#  _shift_srt_timing
# ═══════════════════════════════════════════════════════════


class TestShiftSrtTiming:
    SAMPLE = """1
00:00:01,000 --> 00:00:04,000
Hello"""

    def test_no_offset(self):
        assert _shift_srt_timing(self.SAMPLE, 0) == self.SAMPLE

    def test_forward_500ms(self):
        result = _shift_srt_timing(self.SAMPLE, 500)
        assert "00:00:01,500 --> 00:00:04,500" in result

    def test_backward_500ms(self):
        result = _shift_srt_timing(self.SAMPLE, -500)
        assert "00:00:00,500 --> 00:00:03,500" in result

    def test_clamp_to_zero(self):
        """Negative shift that would go below zero must be clamped to 0."""
        result = _shift_srt_timing(self.SAMPLE, -2000)
        assert "00:00:00,000 --> 00:00:02,000" in result

    def test_empty_content(self):
        assert _shift_srt_timing("", 500) == ""
        assert _shift_srt_timing("   ", 500) == "   "

    def test_multi_block(self):
        srt = """1
00:00:01,000 --> 00:00:04,000
First

2
00:00:06,000 --> 00:00:10,000
Second"""
        result = _shift_srt_timing(srt, 1000)
        assert "00:00:02,000 --> 00:00:05,000" in result
        assert "00:00:07,000 --> 00:00:11,000" in result


# ═══════════════════════════════════════════════════════════
#  _adjust_duration_based_on_text
# ═══════════════════════════════════════════════════════════


class TestAdjustDuration:
    def test_short_text_no_change(self):
        """Short text fits within current duration — no extension."""
        start, end = _adjust_duration_based_on_text(0.0, 5.0, text_length=10)
        # 10 / 17 ≈ 0.59s, min 1.2s → 1.2s needed, current 5.0s > 1.2s → no change
        assert (start, end) == (0.0, 5.0)

    def test_long_text_extends(self):
        """Long text needs more display time — end gets pushed."""
        start, end = _adjust_duration_based_on_text(0.0, 1.0, text_length=50)
        # 50 / 17 ≈ 2.94s, min 1.2s → 2.94s needed, current 1.0s < 2.94s
        # end = 0.0 + 2.94 + 0.2 = 3.14
        assert start == 0.0
        assert abs(end - 3.14) < 0.01

    def test_custom_params(self):
        start, end = _adjust_duration_based_on_text(
            10.0, 12.0, text_length=100, min_chars_per_second=10.0, min_duration=2.0
        )
        # 100 / 10 = 10s needed, min 2s → 10s
        # current 2s < 10s → end = 10 + 10 + 0.2 = 20.2
        assert start == 10.0
        assert abs(end - 20.2) < 0.01

    def test_already_sufficient(self):
        """If duration already meets requirement, no change."""
        start, end = _adjust_duration_based_on_text(0.0, 4.0, text_length=30)
        # 30/17 ≈ 1.76s, min 1.2 → 1.76s. Current 4s > 1.76 → no change
        assert (start, end) == (0.0, 4.0)
