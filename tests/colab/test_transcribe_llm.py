import os
import sys
import threading
import types

import pytest

from ava import llm, transcribe
from ava.errors import Cancelled, UserError


class FakeWord:
    def __init__(self, start, end, word):
        self.start, self.end, self.word = start, end, word


class FakeSegment:
    def __init__(self, start, end, text, words):
        self.start, self.end, self.text, self.words = start, end, text, words


def install_fake_whisper(monkeypatch, segments, device_log):
    class FakeModel:
        def __init__(self, name, device, compute_type):
            device_log.append((name, device, compute_type))
            if device == "cuda" and "fail_cuda" in device_log:
                raise RuntimeError("libcudnn not found")

        def transcribe(self, path, **kw):
            assert kw["word_timestamps"] is True
            return iter(segments), types.SimpleNamespace(duration=10.0, language="ar")

    monkeypatch.setitem(sys.modules, "faster_whisper", types.SimpleNamespace(WhisperModel=FakeModel))
    monkeypatch.setattr(transcribe, "_models", {})


def test_whisper_keeps_word_timestamps_and_reports_progress(monkeypatch):
    log = []
    install_fake_whisper(monkeypatch, [
        FakeSegment(0.0, 2.0, " أهلا بيكم ", [FakeWord(0.1, 0.5, " أهلا"), FakeWord(0.6, 1.2, " بيكم")]),
        FakeSegment(5.0, 10.0, "كلام", []),
    ], log)
    monkeypatch.setattr(transcribe, "cuda_available", lambda: False)
    progress = []
    out = transcribe.transcribe_whisper("v.mp4", "small", "ar", progress.append, lambda m: None, None)
    assert log == [("small", "cpu", "int8")]
    assert out["segments"][0] == {"start": 0.0, "end": 2.0, "text": "أهلا بيكم",
                                  "words": [[0.1, 0.5, " أهلا"], [0.6, 1.2, " بيكم"]]}
    assert out["device"] == "cpu" and out["language"] == "ar"
    assert progress == [0.2, 1.0]


def test_gpu_load_failure_falls_back_to_cpu(monkeypatch):
    log = ["fail_cuda"]
    install_fake_whisper(monkeypatch, [], log)
    monkeypatch.setattr(transcribe, "cuda_available", lambda: True)
    messages = []
    out = transcribe.transcribe_whisper("v.mp4", "large-v3", None, lambda p: None, messages.append, None)
    assert out["device"] == "cpu"
    assert any("المعالج" in m for m in messages)


def test_whisper_cancel(monkeypatch):
    install_fake_whisper(monkeypatch, [FakeSegment(0, 1, "x", [])], [])
    monkeypatch.setattr(transcribe, "cuda_available", lambda: False)
    ev = threading.Event()
    ev.set()
    with pytest.raises(Cancelled):
        transcribe.transcribe_whisper("v.mp4", "small", None, lambda p: None, lambda m: None, ev)


def test_resolve_model(monkeypatch):
    monkeypatch.setattr(transcribe, "cuda_available", lambda: True)
    assert transcribe.resolve_model("auto") == "large-v3"
    monkeypatch.setattr(transcribe, "cuda_available", lambda: False)
    assert transcribe.resolve_model(None) == "small"
    assert transcribe.resolve_model("medium") == "medium"


class FakeResp:
    def __init__(self, status, data=None, headers=None, text=""):
        self.status_code, self._data, self.headers, self.text = status, data or {}, headers or {}, text

    def json(self):
        return self._data


def test_request_retries_transient_errors(monkeypatch):
    calls = []

    def fake_request(method, url, **kw):
        calls.append(url)
        return FakeResp(503, text="busy") if len(calls) < 3 else FakeResp(200, {"ok": True})

    monkeypatch.setattr(llm.requests, "request", fake_request)
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)
    assert llm._request("GET", "https://x").status_code == 200
    assert len(calls) == 3


def test_gemini_requires_key(drive):
    with pytest.raises(UserError, match="GEMINI_API_KEY"):
        llm.gemini_generate("m", [{"text": "hi"}])


def test_generate_text_dispatch(monkeypatch, drive):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setenv("OPENROUTER_API_KEY", "k2")
    seen = []

    def fake_request(method, url, **kw):
        seen.append((url, kw.get("json")))
        if "openrouter" in url:
            return FakeResp(200, {"choices": [{"message": {"content": "OR"}}]})
        return FakeResp(200, {"candidates": [{"content": {"parts": [{"text": "G1"}, {"text": "G2"}]}}]})

    monkeypatch.setattr(llm.requests, "request", fake_request)
    assert llm.generate_text("gemini", "gemini-x", "p") == "G1G2"
    assert seen[-1][1]["generationConfig"]["responseMimeType"] == "application/json"
    assert llm.generate_text("openrouter", "or-model", "p") == "OR"


def test_gemini_transcribe_offsets_chunks_by_position(monkeypatch, drive):
    """Chunk i starts at i*600s; segment times must be shifted by exactly that."""
    monkeypatch.setenv("GEMINI_API_KEY", "k")

    def fake_ffmpeg(args, **kw):
        folder = os.path.dirname(args[-1])
        for i in range(2):
            open(os.path.join(folder, f"chunk_{i:03d}.aac"), "wb").write(b"a")

    replies = iter(['[{"start": 1.0, "end": 2.5, "text": "الأول"}]',
                    '```json\n[{"start": 3.0, "end": 4.0, "text": "التاني"}, {"start": 5, "end": 6, "text": ""}]\n```'])
    deleted = []
    monkeypatch.setattr(llm.media, "run_ffmpeg", fake_ffmpeg)
    monkeypatch.setattr(llm, "_upload_file", lambda path: (f"files/{os.path.basename(path)}", "uri"))
    monkeypatch.setattr(llm, "_wait_active", lambda name, ev: None)
    monkeypatch.setattr(llm, "_delete_file", deleted.append)
    monkeypatch.setattr(llm, "gemini_generate", lambda model, parts, json_output=True: next(replies))
    progress = []
    out = llm.gemini_transcribe("v.mp4", "gemini-x", "ar", transcribe.LANGUAGES,
                                progress.append, lambda m: None, None)
    assert out["segments"] == [{"start": 1.0, "end": 2.5, "text": "الأول"},
                               {"start": 603.0, "end": 604.0, "text": "التاني"}]
    assert progress == [0.5, 1.0]
    assert deleted == ["files/chunk_000.aac", "files/chunk_001.aac"]
