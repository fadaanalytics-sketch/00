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

WHISPER_DEVICES = ["auto", "cpu", "cuda"]
WHISPER_COMPUTE_TYPES = ["default", "int8", "int8_float16", "float16", "float32"]

TRANSCRIPTION_ENGINES = {
    "local": "محلي (Faster-Whisper) - يعمل بدون إنترنت لكن يحتاج معالجة على جهازك",
    "gemini": "سحابي (Gemini) - أسرع على الأجهزة الضعيفة، يحتاج إنترنت ومفتاح Gemini",
}
DEFAULT_TRANSCRIPTION_ENGINE = "local"

AI_PROVIDERS = ["gemini", "openrouter"]

ANALYSIS_MODES = {
    "social_clips": "مقاطع قصيرة للسوشيال ميديا",
    "lecture_sections": "تقسيم المحاضرات الطويلة",
}

CANCELLED_MESSAGE = "تم إلغاء العملية بواسطة المستخدم"

# name -> (width, height)
TEMPLATE_CANVAS_PRESETS = {
    "9:16 (1080x1920) - Reels/Shorts/TikTok": (1080, 1920),
    "1:1 (1080x1080) - منشور مربع": (1080, 1080),
    "16:9 (1920x1080) - يوتيوب": (1920, 1080),
    "4:5 (1080x1350) - انستغرام": (1080, 1350),
}


def ensure_dirs():
    for d in (DATA_DIR, PROJECTS_DIR, TEMPLATES_DIR):
        os.makedirs(d, exist_ok=True)
