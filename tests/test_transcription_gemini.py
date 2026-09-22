import shutil
import subprocess
import threading

import pytest

from app import transcription_gemini as tg
from app.ai_providers import AIProviderError
from app.transcription import CancelledError, TranscriptionError

FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None


class FakeResponse:
    def __init__(self, status_code=200, json_data=None, headers=None, text=""):
        self.status_code = status_code
        self._json = json_data if json_data is not None else {}
        self.headers = headers or {}
        self.text = text

    def json(self):
        return self._json


def test_upload_file_success(monkeypatch, tmp_path):
    audio = tmp_path / "audio.aac"
    audio.write_bytes(b"fake-audio-bytes")

    def fake_post_with_retry(url, **kwargs):
        assert url == tg.GEMINI_UPLOAD_URL
        return FakeResponse(200, headers={"X-Goog-Upload-URL": "https://upload.example/session123"})

    def fake_requests_post(url, **kwargs):
        assert url == "https://upload.example/session123"
        return FakeResponse(
            200, json_data={"file": {"name": "files/abc", "uri": "https://files.example/abc"}}
        )

    monkeypatch.setattr(tg, "post_with_retry", fake_post_with_retry)
    monkeypatch.setattr(tg.requests, "post", fake_requests_post)

    name, uri = tg._upload_file(str(audio), "key123")
    assert name == "files/abc"
    assert uri == "https://files.example/abc"


def test_upload_file_missing_upload_url_raises(monkeypatch, tmp_path):
    audio = tmp_path / "audio.aac"
    audio.write_bytes(b"x")
    monkeypatch.setattr(tg, "post_with_retry", lambda url, **kw: FakeResponse(200, headers={}))
    with pytest.raises(AIProviderError):
        tg._upload_file(str(audio), "key")


def test_wait_until_active_success(monkeypatch):
    calls = {"n": 0}

    def fake_get(url, **kwargs):
        calls["n"] += 1
        state = "PROCESSING" if calls["n"] < 2 else "ACTIVE"
        return FakeResponse(200, json_data={"state": state})

    monkeypatch.setattr(tg.requests, "get", fake_get)
    monkeypatch.setattr(tg, "POLL_INTERVAL_SECONDS", 0)
    tg._wait_until_active("files/abc", "key")
    assert calls["n"] >= 2


def test_wait_until_active_failed_state_raises(monkeypatch):
    monkeypatch.setattr(
        tg.requests, "get", lambda url, **kw: FakeResponse(200, json_data={"state": "FAILED"})
    )
    with pytest.raises(AIProviderError):
        tg._wait_until_active("files/abc", "key")


def test_wait_until_active_respects_cancel(monkeypatch):
    monkeypatch.setattr(
        tg.requests, "get", lambda url, **kw: FakeResponse(200, json_data={"state": "PROCESSING"})
    )
    monkeypatch.setattr(tg, "POLL_INTERVAL_SECONDS", 0)
    event = threading.Event()
    event.set()
    with pytest.raises(CancelledError):
        tg._wait_until_active("files/abc", "key", cancel_event=event)


def test_request_transcript_success(monkeypatch):
    def fake_post_with_retry(url, **kwargs):
        assert "generateContent" in url
        return FakeResponse(200, json_data={
            "candidates": [{"content": {"parts": [{"text": '[{"start":0,"end":1,"text":"hi"}]'}]}}]
        })

    monkeypatch.setattr(tg, "post_with_retry", fake_post_with_retry)
    text = tg._request_transcript("https://files.example/abc", "key", "gemini-2.0-flash", None)
    assert "hi" in text


def test_request_transcript_bad_status_raises(monkeypatch):
    monkeypatch.setattr(tg, "post_with_retry", lambda url, **kw: FakeResponse(403, text="denied"))
    with pytest.raises(AIProviderError):
        tg._request_transcript("uri", "key", "model", None)


def test_transcribe_via_gemini_missing_api_key_raises():
    with pytest.raises(TranscriptionError):
        tg.transcribe_via_gemini("video.mp4", api_key="")


def test_transcribe_via_gemini_full_flow(monkeypatch):
    monkeypatch.setattr(tg, "_extract_audio", lambda video_path, out_path: None)
    monkeypatch.setattr(
        tg, "_upload_file", lambda audio_path, api_key: ("files/abc", "https://files.example/abc")
    )
    monkeypatch.setattr(
        tg, "_wait_until_active", lambda file_name, api_key, cancel_event=None: None
    )
    monkeypatch.setattr(
        tg, "_request_transcript",
        lambda file_uri, api_key, model, language: '[{"start": 0.0, "end": 2.5, "text": "مرحبا"}]',
    )

    statuses = []
    progresses = []
    segments = tg.transcribe_via_gemini(
        "video.mp4", api_key="key123",
        status_cb=statuses.append, progress_cb=progresses.append,
    )
    assert len(segments) == 1
    assert segments[0].text == "مرحبا"
    assert segments[0].end == 2.5
    assert progresses[-1] == 1.0
    assert len(statuses) >= 3


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg not installed")
def test_extract_audio_produces_a_playable_audio_file(tmp_path):
    video = tmp_path / "test.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=15:duration=2",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=2", "-shortest", str(video)],
        check=True, capture_output=True,
    )
    audio_out = tmp_path / "audio.aac"
    tg._extract_audio(str(video), str(audio_out))
    assert audio_out.exists()
    assert audio_out.stat().st_size > 0

    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=codec_type",
         "-of", "default=noprint_wrappers=1:nokey=1", str(audio_out)],
        check=True, capture_output=True, text=True,
    )
    assert probe.stdout.strip() == "audio"


def test_transcribe_via_gemini_bad_json_raises_transcription_error(monkeypatch):
    monkeypatch.setattr(tg, "_extract_audio", lambda video_path, out_path: None)
    monkeypatch.setattr(tg, "_upload_file", lambda audio_path, api_key: ("files/abc", "uri"))
    monkeypatch.setattr(tg, "_wait_until_active", lambda file_name, api_key, cancel_event=None: None)
    monkeypatch.setattr(
        tg, "_request_transcript", lambda file_uri, api_key, model, language: "ليس JSON"
    )
    with pytest.raises(TranscriptionError):
        tg.transcribe_via_gemini("video.mp4", api_key="key123")
