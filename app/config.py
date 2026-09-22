"""App-wide paths and constants."""
import os
import sys

APP_NAME = "AIVideoAnalyzer"

if sys.platform == "win32":
    _base = os.environ.get("APPDATA", os.path.expanduser("~"))
elif sys.platform == "darwin":
    _base = os.path.expanduser("~/Library/Application Support")
else:
    _base = os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))

DATA_DIR = os.path.join(_base, APP_NAME)
PROJECTS_DIR = os.path.join(DATA_DIR, "projects")
TEMPLATES_DIR = os.path.join(DATA_DIR, "templates")
DB_PATH = os.path.join(DATA_DIR, "app.db")

WHISPER_MODELS = ["tiny", "base", "small", "medium", "large-v3"]
DEFAULT_WHISPER_MODEL = "small"

AI_PROVIDERS = ["gemini", "openrouter"]

ANALYSIS_MODES = {
    "social_clips": "مقاطع قصيرة للسوشيال ميديا",
    "lecture_sections": "تقسيم المحاضرات الطويلة",
}


def ensure_dirs():
    for d in (DATA_DIR, PROJECTS_DIR, TEMPLATES_DIR):
        os.makedirs(d, exist_ok=True)
