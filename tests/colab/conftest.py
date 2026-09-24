import os
import shutil
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "colab")))

FFMPEG = shutil.which("ffmpeg") is not None
needs_ffmpeg = pytest.mark.skipif(not FFMPEG, reason="ffmpeg not installed")


@pytest.fixture
def drive(tmp_path, monkeypatch):
    """A temp folder standing in for /content/drive/MyDrive."""
    mount = tmp_path / "drive"
    monkeypatch.setenv("AVA_MOUNT_ROOT", str(mount))
    monkeypatch.setenv("AVA_WORK_DIR", str(tmp_path / "work"))
    monkeypatch.setenv("AVA_DATA_DIR", "AIVideoAnalyzer")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    from ava import config
    config.ensure_dirs()
    return mount


@pytest.fixture(scope="session")
def sample_video(tmp_path_factory):
    if not FFMPEG:
        pytest.skip("ffmpeg not installed")
    path = tmp_path_factory.mktemp("media") / "sample.mp4"
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=30:duration=6",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=6",
         "-shortest", "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", str(path)],
        check=True,
    )
    return path


@pytest.fixture
def video_in_drive(drive, sample_video):
    dest = drive / "AIVideoAnalyzer" / "videos" / "محاضرة تجريبية.mp4"
    shutil.copy(sample_video, dest)
    return "AIVideoAnalyzer/videos/محاضرة تجريبية.mp4"


def make_png(path, w, h, color="blue"):
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
                    "-i", f"color=c={color}:size={w}x{h},format=rgba", "-frames:v", "1", str(path)], check=True)
    return path


def probe_streams(path):
    import json
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                          "stream=codec_type,width,height,r_frame_rate:format=duration", "-of", "json", str(path)],
                         capture_output=True, text=True, check=True).stdout
    data = json.loads(out)
    video = next(s for s in data["streams"] if s["codec_type"] == "video")
    return {"width": video["width"], "height": video["height"], "fps": video["r_frame_rate"],
            "duration": float(data["format"]["duration"]),
            "has_audio": any(s["codec_type"] == "audio" for s in data["streams"])}
