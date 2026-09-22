"""Clip cutting and template compositing via FFmpeg (subprocess, no ffmpeg-python dep)."""
import os
import shutil
import subprocess

from .models import Template, Topic

HIGH_QUALITY_VIDEO_ARGS = ["-c:v", "libx264", "-crf", "18", "-preset", "slow", "-pix_fmt", "yuv420p"]
HIGH_QUALITY_AUDIO_ARGS = ["-c:a", "aac", "-b:a", "192k"]


class ExportError(Exception):
    pass


def _ffmpeg_bin() -> str:
    path = shutil.which("ffmpeg")
    if not path:
        raise ExportError("FFmpeg غير مثبت أو غير موجود في PATH")
    return path


def _run(cmd: list[str]):
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if proc.returncode != 0:
        raise ExportError(f"فشل FFmpeg:\n{proc.stdout[-4000:]}")


def _escape_drawtext(text: str) -> str:
    text = text.replace("\\", "\\\\")
    text = text.replace(":", "\\:")
    text = text.replace("%", "\\%")
    text = text.replace("'", "’")
    return text


def safe_filename(name: str) -> str:
    keep = "".join(c if c.isalnum() or c in " -_." else "_" for c in name)
    return keep.strip().strip(".") or "clip"


def cut_clip(video_path: str, start: float, end: float, out_path: str):
    """Cut [start, end] from video_path with fixed high quality, no template."""
    ffmpeg = _ffmpeg_bin()
    duration = max(end - start, 0.1)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    cmd = [
        ffmpeg, "-y", "-ss", str(start), "-i", video_path, "-t", str(duration),
        *HIGH_QUALITY_VIDEO_ARGS, *HIGH_QUALITY_AUDIO_ARGS, out_path,
    ]
    _run(cmd)


def export_with_template(video_path: str, start: float, end: float,
                          template: Template, out_path: str):
    """Cut [start, end] and composite it onto the template image with text overlays."""
    ffmpeg = _ffmpeg_bin()
    duration = max(end - start, 0.1)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    filters = [
        f"[1:v]scale={template.canvas_w}:{template.canvas_h}[bg]",
        f"[0:v]scale={template.video_w}:{template.video_h}[fg]",
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
    cmd = [
        ffmpeg, "-y",
        "-ss", str(start), "-t", str(duration), "-i", video_path,
        "-loop", "1", "-i", template.image_path,
        "-filter_complex", filter_complex,
        "-map", f"[{last}]", "-map", "0:a?",
        *HIGH_QUALITY_VIDEO_ARGS, *HIGH_QUALITY_AUDIO_ARGS,
        "-shortest", out_path,
    ]
    _run(cmd)


def export_topics(video_path: str, topics: list[Topic], out_dir: str,
                   template: Template = None, progress_cb=None):
    """Export every selected topic as its own file into out_dir."""
    os.makedirs(out_dir, exist_ok=True)
    selected = [t for t in topics if t.selected]
    results = []
    for i, topic in enumerate(selected):
        filename = f"{i + 1:02d}_{safe_filename(topic.name)}.mp4"
        out_path = os.path.join(out_dir, filename)
        if template:
            export_with_template(video_path, topic.start, topic.end, template, out_path)
        else:
            cut_clip(video_path, topic.start, topic.end, out_path)
        results.append(out_path)
        if progress_cb:
            progress_cb((i + 1) / len(selected))
    return results
