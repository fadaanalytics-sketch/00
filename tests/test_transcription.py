from app.models import Segment
from app.transcription import (
    format_timecode, segments_from_json, segments_to_json, segments_to_srt,
)


def test_segments_json_round_trip():
    segments = [Segment(start=0.0, end=1.5, text="مرحبا"), Segment(start=1.5, end=3.0, text="بالعالم")]
    data = segments_to_json(segments)
    restored = segments_from_json(data)
    assert restored == segments


def test_segments_from_json_empty_string():
    assert segments_from_json("") == []


def test_format_timecode():
    assert format_timecode(0) == "00:00:00.000"
    assert format_timecode(3661.25) == "01:01:01.250"


def test_segments_to_srt_format():
    segments = [Segment(start=0.0, end=1.5, text="مرحبا")]
    srt = segments_to_srt(segments)
    lines = srt.strip().splitlines()
    assert lines[0] == "1"
    assert lines[1] == "00:00:00,000 --> 00:00:01,500"
    assert lines[2] == "مرحبا"
