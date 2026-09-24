"""Local (Colab VM) transcription with faster-whisper, on the GPU when available."""
import functools
import logging
import subprocess
import threading

from .errors import Cancelled

logger = logging.getLogger(__name__)

LANGUAGES = {
    "": "تلقائي", "ar": "العربية", "en": "الإنجليزية", "fr": "الفرنسية", "es": "الإسبانية",
    "de": "الألمانية", "tr": "التركية", "ur": "الأردية", "hi": "الهندية", "zh": "الصينية",
    "ru": "الروسية",
}

_models: dict = {}
_lock = threading.Lock()


def cuda_available() -> bool:
    try:
        import ctranslate2
        return ctranslate2.get_cuda_device_count() > 0
    except Exception:  # noqa: BLE001 - missing/broken CUDA just means "no GPU"
        return False


@functools.lru_cache(maxsize=1)
def gpu_name() -> str | None:
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                             capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        return None
    lines = out.stdout.strip().splitlines() if out.returncode == 0 else []
    return lines[0].strip() if lines else None


def resolve_model(name: str | None) -> str:
    if not name or name == "auto":
        return "large-v3" if cuda_available() else "small"
    return name


def _load(name: str, status_cb):
    from faster_whisper import WhisperModel
    with _lock:
        if name in _models:
            return _models[name]
        if cuda_available():
            status_cb(f"جارٍ تحميل نموذج Whisper ({name}) على كارت الشاشة...")
            try:
                _models[name] = (WhisperModel(name, device="cuda", compute_type="float16"), "cuda")
                return _models[name]
            except Exception:  # noqa: BLE001 - e.g. CUDA/cuDNN mismatch: fall back, don't fail
                logger.exception("GPU model load failed, falling back to CPU")
                status_cb("تعذر استخدام كارت الشاشة، سيتم التفريغ على المعالج (أبطأ)...")
        else:
            status_cb(f"جارٍ تحميل نموذج Whisper ({name}) على المعالج...")
        _models[name] = (WhisperModel(name, device="cpu", compute_type="int8"), "cpu")
        return _models[name]


def transcribe_whisper(video_path: str, model_name: str, language: str | None,
                       progress_cb, status_cb, cancel_event) -> dict:
    model, device = _load(model_name, status_cb)
    status_cb("جارٍ التفريغ الصوتي...")
    segments_iter, info = model.transcribe(
        video_path, beam_size=5, vad_filter=True, word_timestamps=True, language=language or None,
    )
    duration = getattr(info, "duration", 0) or 0
    segments = []
    for seg in segments_iter:
        if cancel_event is not None and cancel_event.is_set():
            raise Cancelled()
        words = [[round(w.start, 2), round(w.end, 2), w.word] for w in (seg.words or [])]
        segments.append({"start": round(seg.start, 2), "end": round(seg.end, 2),
                         "text": seg.text.strip(), "words": words})
        if duration:
            progress_cb(min(seg.end / duration, 1.0))
    return {"engine": "whisper", "model": model_name, "device": device,
            "language": getattr(info, "language", "") or (language or ""), "segments": segments}
