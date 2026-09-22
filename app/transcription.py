"""Speech-to-text via faster-whisper, producing timestamped segments."""
import json
from typing import Callable, Optional

from .models import Segment


class TranscriptionError(Exception):
    pass


def transcribe(
    video_path: str,
    model_size: str = "small",
    device: str = "auto",
    compute_type: str = "default",
    progress_cb: Optional[Callable[[float], None]] = None,
) -> list[Segment]:
    try:
        from faster_whisper import WhisperModel
    except ImportError as e:
        raise TranscriptionError("مكتبة faster-whisper غير مثبتة") from e

    model = WhisperModel(model_size, device=device, compute_type=compute_type)
    segments_iter, info = model.transcribe(video_path, beam_size=5, vad_filter=True)

    duration = getattr(info, "duration", 0) or 0
    results: list[Segment] = []
    for seg in segments_iter:
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
