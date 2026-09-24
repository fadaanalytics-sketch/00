import base64
import time
import urllib.parse

import pytest
from fastapi.testclient import TestClient

from ava import llm, server, transcribe

from .conftest import make_png, needs_ffmpeg, probe_streams

pytestmark = needs_ffmpeg


@pytest.fixture
def client(drive):
    with TestClient(server.app) as c:
        yield c


def data_url(path, mime="image/png"):
    return f"data:{mime};base64,{base64.b64encode(open(path, 'rb').read()).decode()}"


def wait_job(client, job, timeout=60):
    deadline = time.time() + timeout
    while job["status"] in ("queued", "running") and time.time() < deadline:
        time.sleep(0.1)
        job = client.get(f"/api/jobs/{job['id']}").json()
    return job


def create_project(client, video_path):
    r = client.post("/api/projects", json={"video": video_path})
    assert r.status_code == 200, r.text
    return r.json()


def test_index_and_status(client):
    assert "AI Video Analyzer" in client.get("/").text
    s = client.get("/api/status").json()
    assert s["data_root"] == "AIVideoAnalyzer" and s["gemini_key"] is False
    assert client.get("/static/app.js").status_code == 200


def test_create_project_probes_video(client, video_in_drive):
    p = create_project(client, video_in_drive)
    assert p["name"] == "محاضرة تجريبية" and p["stage"] == "new" and p["has_preview"] is False
    assert (p["media"]["width"], p["media"]["height"]) == (640, 360)
    assert client.get("/api/projects").json()[0]["id"] == p["id"]


def test_create_project_rejects_bad_paths(client, drive):
    (drive / "AIVideoAnalyzer" / "notes.txt").write_text("x")
    assert client.post("/api/projects", json={"video": "AIVideoAnalyzer/missing.mp4"}).status_code == 400
    assert client.post("/api/projects", json={"video": "AIVideoAnalyzer/notes.txt"}).status_code == 400
    assert client.post("/api/projects", json={"video": "../../etc/passwd"}).status_code == 400
    assert client.get("/api/browse", params={"path": "../.."}).status_code == 400


def test_transcribe_then_analyze_snaps_to_words(client, video_in_drive, monkeypatch):
    p = create_project(client, video_in_drive)
    words = [[0.5, 0.9, " أهلا"], [1.0, 1.6, " بيكم"], [3.0, 3.5, " في"], [3.6, 4.4, " الدرس"]]
    fake_transcript = {"engine": "whisper", "model": "small", "device": "cpu", "language": "ar",
                       "segments": [{"start": 0.5, "end": 1.6, "text": "أهلا بيكم", "words": words[:2]},
                                    {"start": 3.0, "end": 4.4, "text": "في الدرس", "words": words[2:]}]}
    monkeypatch.setattr(transcribe, "transcribe_whisper", lambda *a, **k: fake_transcript)
    job = wait_job(client, client.post(f"/api/projects/{p['id']}/transcribe", json={"engine": "whisper"}).json())
    assert job["status"] == "done", job
    assert client.get(f"/api/projects/{p['id']}").json()["stage"] == "transcribed"

    # AI returns a clip that starts mid-word and ends mid-word.
    prompts = []

    def fake_generate(provider, model, prompt):
        prompts.append((provider, model, prompt))
        return '[{"name": "الترحيب", "text": "مقدمة", "start": 0.7, "end": 3.8}]'

    monkeypatch.setattr(llm, "generate_text", fake_generate)
    job = wait_job(client, client.post(f"/api/projects/{p['id']}/analyze", json={"mode": "social_clips"}).json())
    assert job["status"] == "done", job
    assert prompts[0][:2] == ("gemini", "gemini-2.5-flash")
    assert "[0.5 - 1.6] أهلا بيكم" in prompts[0][2]
    topics = client.get(f"/api/projects/{p['id']}").json()["topics"]
    assert (topics[0]["start"], topics[0]["end"]) == (0.4, 4.55)


def test_analyze_without_transcript_fails_clearly(client, video_in_drive):
    p = create_project(client, video_in_drive)
    job = wait_job(client, client.post(f"/api/projects/{p['id']}/analyze", json={}).json())
    assert job["status"] == "error" and "تفريغ" in job["message"]


def test_duplicate_job_is_rejected(client, video_in_drive, monkeypatch):
    p = create_project(client, video_in_drive)
    gate = __import__("threading").Event()
    monkeypatch.setattr(transcribe, "transcribe_whisper", lambda *a, **k: gate.wait(5) and None)
    first = client.post(f"/api/projects/{p['id']}/transcribe", json={"engine": "whisper"}).json()
    second = client.post(f"/api/projects/{p['id']}/transcribe", json={"engine": "whisper"})
    assert second.status_code == 400
    client.post(f"/api/jobs/{first['id']}/cancel")
    gate.set()
    assert wait_job(client, first)["status"] in ("cancelled", "error")


def test_topics_validation(client, video_in_drive):
    p = create_project(client, video_in_drive)
    r = client.put(f"/api/projects/{p['id']}/topics", json={"topics": [{"name": "x", "start": 1, "end": 99}]})
    assert r.json()["topics"][0]["end"] == pytest.approx(6, abs=0.2)  # clamped to the video length
    assert client.put(f"/api/projects/{p['id']}/topics", json={"topics": [{"start": "x", "end": 1}]}).status_code == 400


def make_template(client, tmp_path, texts=None):
    bg = make_png(tmp_path / "bg.png", 540, 960, "purple")
    tpl = {"name": "ريلز", "canvas_w": 540, "canvas_h": 960, "bg_color": "#000000",
           "video": {"x": 0, "y": 240, "w": 540, "h": 480, "fit": "cover"}, "texts": texts or []}
    r = client.post("/api/templates", json={"template": tpl, "background": data_url(bg)})
    assert r.status_code == 200, r.text
    return r.json()


def test_template_validation(client, tmp_path):
    bg = data_url(make_png(tmp_path / "bg.png", 64, 64))
    base = {"name": "t", "canvas_w": 1080, "canvas_h": 1920, "video": {"x": 0, "y": 0, "w": 100, "h": 100}}
    for bad in ({"canvas_w": 10}, {"video": {"x": 0}}, {"name": " "}, {"video": {"x": 0, "y": 0, "w": 4, "h": 4}}):
        assert client.post("/api/templates", json={"template": dict(base, **bad), "background": bg}).status_code == 400
    ok = client.post("/api/templates", json={"template": dict(base, canvas_w=941), "background": bg}).json()
    assert ok["canvas_w"] == 942 and ok["video"]["fit"] == "cover"
    assert client.get(f"/api/templates/{ok['id']}/background").status_code == 200
    assert client.delete(f"/api/templates/{ok['id']}").status_code == 200


def test_export_with_template_and_overlay_saves_to_drive(client, drive, video_in_drive, tmp_path):
    p = create_project(client, video_in_drive)
    topics = client.put(f"/api/projects/{p['id']}/topics", json={"topics": [
        {"name": "الأول؟ (معدّل)", "start": 1.0, "end": 3.0, "selected": True},
        {"name": "مش محدد", "start": 3.0, "end": 5.0, "selected": False},
    ]}).json()["topics"]
    tpl = make_template(client, tmp_path, texts=[{"id": "a", "text": "{title}", "x": 270, "y": 60, "size": 40}])
    overlay = data_url(make_png(tmp_path / "ov.png", 540, 960, "white@0.0"))
    job = client.post(f"/api/projects/{p['id']}/export", json={
        "topic_ids": [topics[0]["id"]], "template_id": tpl["id"],
        "overlays": {topics[0]["id"]: overlay}, "folder": "مقاطع الريلز"}).json()
    job = wait_job(client, job, timeout=120)
    assert job["status"] == "done", job
    assert job["result"]["files"] == ["AIVideoAnalyzer/outputs/مقاطع الريلز/01_الأول معدّل.mp4"]
    info = probe_streams(drive / job["result"]["files"][0])
    assert (info["width"], info["height"], info["fps"]) == (540, 960, "30/1")
    assert info["duration"] == pytest.approx(2.0, abs=0.1)

    # exporting again never overwrites earlier files
    job2 = wait_job(client, client.post(f"/api/projects/{p['id']}/export", json={
        "topic_ids": [topics[0]["id"]], "cut_mode": "fast", "folder": "مقاطع الريلز"}).json(), timeout=60)
    assert job2["result"]["files"] == ["AIVideoAnalyzer/outputs/مقاطع الريلز/01_الأول معدّل_2.mp4"]
    assert client.get(f"/api/projects/{p['id']}").json()["stage"] == "exported"

    download = client.get("/api/files", params={"path": job["result"]["files"][0]})
    assert download.status_code == 200
    assert urllib.parse.quote("01_الأول معدّل.mp4") in download.headers["content-disposition"]


def test_export_validation(client, video_in_drive):
    p = create_project(client, video_in_drive)
    assert client.post(f"/api/projects/{p['id']}/export", json={"topic_ids": [], "cut_mode": "weird"}).status_code == 400
    assert client.post(f"/api/projects/{p['id']}/export", json={"topic_ids": [], "template_id": "tpl_x"}).status_code == 404
    job = wait_job(client, client.post(f"/api/projects/{p['id']}/export", json={"topic_ids": ["nope"]}).json())
    assert job["status"] == "error" and "مقاطع" in job["message"]


def test_preview_and_range_requests(client, video_in_drive):
    p = create_project(client, video_in_drive)
    assert client.get(f"/api/projects/{p['id']}/preview").status_code == 404
    job = wait_job(client, client.post(f"/api/projects/{p['id']}/preview").json(), timeout=60)
    assert job["status"] == "done", job
    project = client.get(f"/api/projects/{p['id']}").json()
    assert project["has_preview"] and project["preview_version"] > 0
    url = f"/api/projects/{p['id']}/preview"
    full = client.get(url)
    size = len(full.content)
    r = client.get(url, headers={"Range": "bytes=10-19"})
    assert r.status_code == 206 and r.content == full.content[10:20]
    assert r.headers["content-range"] == f"bytes 10-19/{size}"
    assert client.get(url, headers={"Range": "bytes=-5"}).content == full.content[-5:]
    assert client.get(url, headers={"Range": f"bytes={size + 10}-"}).status_code == 416


def test_delete_project_removes_preview(client, video_in_drive, drive):
    p = create_project(client, video_in_drive)
    wait_job(client, client.post(f"/api/projects/{p['id']}/preview").json(), timeout=60)
    assert client.delete(f"/api/projects/{p['id']}").status_code == 200
    assert client.get(f"/api/projects/{p['id']}").status_code == 404
    assert not list((drive / "AIVideoAnalyzer" / "cache" / "previews").iterdir())
    assert (drive / video_in_drive).exists()  # the original video is never touched
