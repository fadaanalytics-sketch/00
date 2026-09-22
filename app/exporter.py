"""Clip cutting and template compositing via FFmpeg (subprocess, no ffmpeg-python dep)."""
import logging
import os
import shutil
import subprocess
import threading
import time
from typing import Optional

from .config import CANCELLED_MESSAGE
from .models import Template, Topic

logger = logging.getLogger(__name__)

HIGH_QUALITY_VIDEO_ARGS = ["-c:v", "libx264", "-crf", "18", "-preset", "slow", "-pix_fmt", "yuv420p"]
HIGH_QUALITY_AUDIO_ARGS = ["-c:a", "aac", "-b:a", "192k"]


class ExportError(Exception):
    pass


class CancelledError(ExportError):
    pass


def _ffmpeg_bin() -> str:
    path = shutil.which("ffmpeg")
    if not path:
        raise ExportError(
            "FFmpeg غير مثبت أو غير موجود في PATH. لو ثبّته للتو، تأكد من إغلاق "
            "التطبيق تمامًا وإعادة فتحه (أو إعادة تشغيل الجهاز) - البرنامج يقرأ "
            "متغير PATH وقت فتحه فقط، فتعديله لا يؤثر على نسخة مفتوحة بالفعل."
        )
    return path


def _run(cmd: list[str], cancel_event: Optional[threading.Event] = None):
    """Run ffmpeg, continuously draining its output.

    ffmpeg writes a steady stream of progress/encoding stats to stderr. If
    nothing reads stdout/stderr while the process runs, the OS pipe buffer
    (~64KB) fills up and ffmpeg blocks on write() forever - a classic
    subprocess deadlock. It only shows up once a clip is long enough to
    produce more than ~64KB of log output (tiny test clips never hit it),
    at which point the process hangs mid-encode and leaves behind a
    partially-written, unplayable output file. A background thread draining
    the pipe as it's produced avoids this entirely.
    """
    logger.debug("Running ffmpeg: %s", " ".join(cmd))
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace",
    )
    output_chunks: list[str] = []

    def _drain():
        # An uncaught exception here would silently kill this thread while the
        # main loop below keeps polling - draining stops but the process
        # doesn't, silently reintroducing the exact pipe deadlock this exists
        # to prevent. errors="replace" above should make decoding infallible,
        # but never let *any* hiccup here go unread again.
        try:
            for line in proc.stdout:
                output_chunks.append(line)
        except Exception:  # noqa: BLE001 - see comment above
            logger.exception("Error draining ffmpeg output")

    reader = threading.Thread(target=_drain, daemon=True)
    reader.start()

    while proc.poll() is None:
        if cancel_event is not None and cancel_event.is_set():
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
            reader.join(timeout=2)
            raise CancelledError(CANCELLED_MESSAGE)
        time.sleep(0.2)

    reader.join(timeout=5)
    output = "".join(output_chunks)
    if proc.returncode != 0:
        raise ExportError(f"فشل FFmpeg:\n{output[-4000:]}")


def _escape_drawtext(text: str) -> str:
    text = text.replace("\\", "\\\\")
    text = text.replace(":", "\\:")
    text = text.replace("%", "\\%")
    text = text.replace("'", "’")
    return text


def safe_filename(name: str) -> str:
    keep = "".join(c if c.isalnum() or c in " -_." else "_" for c in name)
    return keep.strip().strip(".") or "clip"


def _even(n: int) -> int:
    """libx264 (yuv420p) requires even width/height. Round up rather than down
    so we never crop off a row/column of real content for an odd source size."""
    return n if n % 2 == 0 else n + 1


def build_cut_cmd(ffmpeg: str, video_path: str, start: float, end: float, out_path: str) -> list[str]:
    duration = max(end - start, 0.1)
    return [
        ffmpeg, "-y", "-ss", str(start), "-i", video_path, "-t", str(duration),
        # Guards against source videos with an odd width/height (e.g. some
        # screen recordings), which would otherwise fail the same way a
        # template with an odd-sized canvas does (see build_template_cmd).
        "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
        *HIGH_QUALITY_VIDEO_ARGS, *HIGH_QUALITY_AUDIO_ARGS, out_path,
    ]


def build_template_cmd(ffmpeg: str, video_path: str, start: float, end: float,
                        template: Template, out_path: str) -> list[str]:
    duration = max(end - start, 0.1)
    # The final encoded frame is the canvas size (the video is only overlaid onto
    # it), so an odd canvas_w/canvas_h - e.g. a 941px-wide uploaded template image -
    # makes libx264 fail outright with "width not divisible by 2". Round both
    # canvas and video-placement dimensions up to even to guarantee this can't happen.
    canvas_w, canvas_h = _even(template.canvas_w), _even(template.canvas_h)
    video_w, video_h = _even(template.video_w), _even(template.video_h)
    filters = [
        f"[1:v]scale={canvas_w}:{canvas_h}[bg]",
        f"[0:v]scale={video_w}:{video_h}[fg]",
        f"[bg][fg]overlay={template.video_x}:{template.video_y}[stage0]",
    ]
    last = "stage0"
    for i, tb in enumerate(template.text_boxes):
        stage = f"stage{i + 1}"
        color = tb.font_color.lstrip("#")
        text = _escape_drawtext(tb.text)
        filters.append(
            f"[{last}]drawtext=text='{text}':x={tb.x}:y={tb.y}:"
            f"fontsize={tb.font_size}:fontcolor=0x{color}[{stage}]"
        )
        last = stage

    filter_complex = ";".join(filters)
    # -ss/-t MUST precede the video's own -i (not the template image's -i), otherwise
    # ffmpeg attaches them to the wrong input and the clip duration comes out wrong.
    return [
        ffmpeg, "-y",
        "-ss", str(start), "-t", str(duration), "-i", video_path,
        "-loop", "1", "-i", template.image_path,
        "-filter_complex", filter_complex,
        "-map", f"[{last}]", "-map", "0:a?",
        *HIGH_QUALITY_VIDEO_ARGS, *HIGH_QUALITY_AUDIO_ARGS,
        "-shortest", out_path,
    ]


def cut_clip(video_path: str, start: float, end: float, out_path: str,
             cancel_event: Optional[threading.Event] = None):
    """Cut [start, end] from video_path with fixed high quality, no template."""
    ffmpeg = _ffmpeg_bin()
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    _run(build_cut_cmd(ffmpeg, video_path, start, end, out_path), cancel_event)


def export_with_template(video_path: str, start: float, end: float,
                          template: Template, out_path: str,
                          cancel_event: Optional[threading.Event] = None):
    """Cut [start, end] and composite it onto the template image with text overlays."""
    ffmpeg = _ffmpeg_bin()
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    _run(build_template_cmd(ffmpeg, video_path, start, end, template, out_path), cancel_event)


def export_topics(video_path: str, topics: list[Topic], out_dir: str,
                   template: Template = None, progress_cb=None,
                   cancel_event: Optional[threading.Event] = None):
    """Export every selected topic as its own file into out_dir."""
    os.makedirs(out_dir, exist_ok=True)
    selected = [t for t in topics if t.selected]
    results = []
    for i, topic in enumerate(selected):
        if cancel_event is not None and cancel_event.is_set():
            raise CancelledError(CANCELLED_MESSAGE)
        filename = f"{i + 1:02d}_{safe_filename(topic.name)}.mp4"
        out_path = os.path.join(out_dir, filename)
        if template:
            export_with_template(video_path, topic.start, topic.end, template, out_path, cancel_event)
        else:
            cut_clip(video_path, topic.start, topic.end, out_path, cancel_event)
        results.append(out_path)
        if progress_cb:
            progress_cb((i + 1) / len(selected))
    return results
