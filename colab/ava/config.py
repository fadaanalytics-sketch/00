"""Paths and constants.

Everything is derived from environment variables on every call, so the same code
runs inside Colab (Drive mounted at /content/drive/MyDrive) and in local tests
(a temp dir standing in for Drive).
"""
import os
from dataclasses import dataclass

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v", ".mpg", ".mpeg", ".3gp"}
IMAGE_MIME_EXT = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}

WHISPER_MODELS = ["tiny", "base", "small", "medium", "large-v3", "large-v3-turbo"]
ANALYSIS_MODES = ["social_clips", "lecture_sections"]
CUT_MODES = ["accurate", "fast"]

DEFAULT_SETTINGS = {
    "analysis_provider": "gemini",
    "gemini_model": "gemini-2.5-flash",
    "openrouter_model": "openai/gpt-4o-mini",
    "whisper_model": "auto",
    "language": "",
    "analysis_mode": "social_clips",
    "snap_to_words": True,
}


@dataclass(frozen=True)
class Paths:
    mount_root: str
    data_root: str
    videos: str
    projects: str
    templates: str
    outputs: str
    previews: str
    settings: str
    work: str


def paths() -> Paths:
    mount = os.environ.get("AVA_MOUNT_ROOT", "/content/drive/MyDrive")
    data = os.path.join(mount, os.environ.get("AVA_DATA_DIR", "AIVideoAnalyzer"))
    return Paths(
        mount_root=mount,
        data_root=data,
        videos=os.path.join(data, "videos"),
        projects=os.path.join(data, "projects"),
        templates=os.path.join(data, "templates"),
        outputs=os.path.join(data, "outputs"),
        previews=os.path.join(data, "cache", "previews"),
        settings=os.path.join(data, "settings.json"),
        work=os.environ.get("AVA_WORK_DIR", "/content/ava_work"),
    )


def ensure_dirs():
    p = paths()
    for d in (p.videos, p.projects, p.templates, p.outputs, p.previews, p.work):
        os.makedirs(d, exist_ok=True)


def gemini_key() -> str:
    return os.environ.get("GEMINI_API_KEY", "")


def openrouter_key() -> str:
    return os.environ.get("OPENROUTER_API_KEY", "")
