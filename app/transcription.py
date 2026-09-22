"""Speech-to-text via faster-whisper, producing timestamped segments."""
import json
import threading
from typing import Callable, Optional

from .config import CANCELLED_MESSAGE
from .models import Segment

# faster-whisper downloads the model from Hugging Face on first use (hundreds of MB).
# With no network, or a blocked/slow proxy, that download can hang indefinitely with
# no feedback at all - which looks exactly like the app being frozen. Bound it.
MODEL_LOAD_TIMEOUT_SECONDS = 300

# A practical subset; faster-whisper/Whisper supports many more ISO-639-1 codes.
LANGUAGES = {
    "": "تلقائي (اكتشاف تلقائي)",
    "ar": "العربية",
    "en": "الإنجليزية",
    "fr": "الفرنسية",
    "es": "الإسبانية",
    "de": "الألمانية",
    "tr": "التركية",
    "ur": "الأردية",
    "hi": "الهندية",
    "zh": "الصينية",
    "ru": "الروسية",
}


class TranscriptionError(Exception):
    pass


class CancelledError(TranscriptionError):
    pass


def _load_model(model_size: str, device: str, compute_type: str, result: dict):
    from faster_whisper import WhisperModel
    try:
        # Fast path: model already cached locally from a previous run, no network at all.
        result["model"] = WhisperModel(
            model_size, device=device, compute_type=compute_type, local_files_only=True
        )
    except Exception:
        try:
            result["model"] = WhisperModel(model_size, device=device, compute_type=compute_type)
        except Exception as e:  # noqa: BLE001 - reported back to the caller thread
            result["error"] = e


def load_model(
    model_size: str = "small",
    device: str = "auto",
    compute_type: str = "default",
    status_cb: Optional[Callable[[str], None]] = None,
):
    """Load (or download, on first use) a Whisper model with a bounded timeout.

    Runs in a daemon thread so a hung download never blocks the app indefinitely -
    it just fails with a clear, actionable error after MODEL_LOAD_TIMEOUT_SECONDS.
    """
    if status_cb:
        status_cb("جارٍ تحميل نموذج Whisper (قد يستغرق عدة دقائق في أول استخدام)...")
    result: dict = {}
    thread = threading.Thread(target=_load_model, args=(model_size, device, compute_type, result), daemon=True)
    thread.start()
    thread.join(timeout=MODEL_LOAD_TIMEOUT_SECONDS)
    if thread.is_alive():
        raise TranscriptionError(
            f"تعذر تحميل نموذج Whisper خلال {MODEL_LOAD_TIMEOUT_SECONDS} ثانية. "
            "على الأرجح لا يوجد اتصال بالإنترنت (أو محجوب عبر بروكسي) لتنزيل النموذج "
            "لأول مرة — بعد نجاح التنزيل مرة واحدة سيعمل التطبيق بدون إنترنت لاحقًا. "
            "تحقق من اتصالك بالشبكة وحاول مرة أخرى."
        )
    if "error" in result:
        raise TranscriptionError(f"فشل تحميل نموذج Whisper: {result['error']}") from result["error"]
    return result["model"]


def transcribe(
    video_path: str,
    model_size: str = "small",
    device: str = "auto",
    compute_type: str = "default",
    language: Optional[str] = None,
    progress_cb: Optional[Callable[[float], None]] = None,
    cancel_event: Optional[threading.Event] = None,
    status_cb: Optional[Callable[[str], None]] = None,
) -> list[Segment]:
    try:
        import faster_whisper  # noqa: F401 - import-availability check only
    except ImportError as e:
        raise TranscriptionError("مكتبة faster-whisper غير مثبتة") from e

    model = load_model(model_size, device, compute_type, status_cb)
    if status_cb:
        status_cb("جارٍ التفريغ الصوتي...")
    segments_iter, info = model.transcribe(
        video_path, beam_size=5, vad_filter=True, language=language or None
    )

    duration = getattr(info, "duration", 0) or 0
    results: list[Segment] = []
    for seg in segments_iter:
        if cancel_event is not None and cancel_event.is_set():
            raise CancelledError(CANCELLED_MESSAGE)
        results.append(Segment(start=seg.start, end=seg.end, text=seg.text.strip()))
        if progress_cb and duration:
            progress_cb(min(seg.end / duration, 1.0))
    if progress_cb:
        progress_cb(1.0)
    return results


def segments_to_json(segments: list[Segment]) -> str:
    return json.dumps([s.__dict__ for s in segments], ensure_ascii=False)


def segments_from_json(data: str) -> list[Segment]:
    if not data:
        return []
    return [Segment(**s) for s in json.loads(data)]


def format_timecode(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"


def transcript_as_text(segments: list[Segment]) -> str:
    lines = []
    for s in segments:
        lines.append(f"[{format_timecode(s.start)} - {format_timecode(s.end)}] {s.text}")
    return "\n".join(lines)


def _srt_timecode(seconds: float) -> str:
    if seconds < 0:
        seconds = 0
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int(round((seconds - int(seconds)) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def segments_to_srt(segments: list[Segment]) -> str:
    blocks = []
    for i, seg in enumerate(segments, start=1):
        blocks.append(
            f"{i}\n{_srt_timecode(seg.start)} --> {_srt_timecode(seg.end)}\n{seg.text}\n"
        )
    return "\n".join(blocks)
