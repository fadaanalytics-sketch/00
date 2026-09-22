import time

import pytest

from app import transcription
from app.models import Segment
from app.transcription import (
    TranscriptionError, format_timecode, load_model, segments_from_json,
    segments_to_json, segments_to_srt,
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


def test_load_model_returns_result_on_success(monkeypatch):
    def fake_load(model_size, device, compute_type, result):
        result["model"] = "fake-model"

    monkeypatch.setattr(transcription, "_load_model", fake_load)
    assert load_model("tiny") == "fake-model"


def test_load_model_raises_on_error(monkeypatch):
    def fake_load(model_size, device, compute_type, result):
        result["error"] = RuntimeError("boom")

    monkeypatch.setattr(transcription, "_load_model", fake_load)
    with pytest.raises(TranscriptionError, match="boom"):
        load_model("tiny")


def test_load_model_times_out_instead_of_hanging_forever(monkeypatch):
    """Regression test: a stuck download (no network / blocked proxy) must fail
    with a clear error after a bounded wait, not hang the app indefinitely."""
    monkeypatch.setattr(transcription, "MODEL_LOAD_TIMEOUT_SECONDS", 0.2)

    def fake_load(model_size, device, compute_type, result):
        time.sleep(5)  # simulates a hung download; thread is daemon so it won't block the test

    monkeypatch.setattr(transcription, "_load_model", fake_load)
    with pytest.raises(TranscriptionError, match="تعذر تحميل نموذج Whisper"):
        load_model("tiny")


def test_load_model_reports_status(monkeypatch):
    def fake_load(model_size, device, compute_type, result):
        result["model"] = "fake-model"

    monkeypatch.setattr(transcription, "_load_model", fake_load)
    messages = []
    load_model("tiny", status_cb=messages.append)
    assert messages  # at least the "downloading model" message was sent
