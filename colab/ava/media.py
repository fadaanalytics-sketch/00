"""FFmpeg/ffprobe helpers. Argument builders are pure functions so they're testable
without running anything; run_ffmpeg() handles execution, progress and cancel."""
import collections
import functools
import json
import logging
import re
import shutil
import subprocess
import threading
import time

from .errors import Cancelled

logger = logging.getLogger(__name__)

NVENC_ARGS = ["-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", "19", "-b:v", "0"]
NVENC_PREVIEW_ARGS = ["-c:v", "h264_nvenc", "-preset", "p1", "-rc", "vbr", "-cq", "32", "-b:v", "0"]
# Colab's free CPU is only 2 cores, so favour speed; CRF 18 keeps quality high.
X264_ARGS = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18"]
X264_PREVIEW_ARGS = ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "30"]
AUDIO_ARGS = ["-c:a", "aac", "-b:a", "192k"]

_PROGRESS_KEY_RE = re.compile(
    r"^(frame|fps|stream_\d+_\d+_q|bitrate|total_size|out_time(_us|_ms)?|"
    r"dup_frames|drop_frames|speed|progress)="
)


class MediaError(Exception):
    pass


def ffmpeg_bin() -> str:
    path = shutil.which("ffmpeg")
    if not path:
        raise MediaError("FFmpeg غير موجود على الجهاز")
    return path


def ffprobe_bin() -> str:
    path = shutil.which("ffprobe")
    if not path:
        raise MediaError("ffprobe غير موجود على الجهاز")
    return path


def even(n) -> int:
    """libx264/NVENC with yuv420p reject odd width/height outright; round up so no
    row/column of real content is ever cropped."""
    n = int(round(n))
    return n if n % 2 == 0 else n + 1


def probe(path: str) -> dict:
    proc = subprocess.run(
        [ffprobe_bin(), "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if proc.returncode != 0:
        raise MediaError(f"تعذر قراءة ملف الفيديو:\n{proc.stderr[-800:]}")
    data = json.loads(proc.stdout or "{}")
    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    if video is None:
        raise MediaError("الملف لا يحتوي على فيديو")
    duration = float(data.get("format", {}).get("duration") or video.get("duration") or 0)
    fps = video.get("avg_frame_rate") or ""
    if not re.match(r"^\d+/\d+$", fps) or fps.startswith("0/") or fps.endswith("/0"):
        fps = video.get("r_frame_rate") or "30/1"
        if fps.startswith("0/") or fps.endswith("/0"):
            fps = "30/1"
    width, height = int(video.get("width") or 0), int(video.get("height") or 0)
    # Phone videos often store rotation as metadata; ffmpeg auto-rotates on decode,
    # so report the dimensions the viewer actually sees.
    rotation = 0
    for sd in video.get("side_data_list") or []:
        if "rotation" in sd:
            rotation = int(float(sd["rotation"]))
    rotation = rotation or int(float((video.get("tags") or {}).get("rotate", 0) or 0))
    if abs(rotation) % 180 == 90:
        width, height = height, width
    return {
        "duration": duration, "width": width, "height": height, "fps": fps,
        "has_audio": any(s.get("codec_type") == "audio" for s in streams),
    }


def run_ffmpeg(args: list[str], duration: float = None, progress_cb=None, cancel_event=None):
    """Run ffmpeg with progress reporting.

    Output is drained continuously on a background thread: ffmpeg writes a steady
    stream of stats, and an undrained pipe (~64KB) blocks it forever on long clips.
    Decoding uses utf-8 with errors="replace" - with the platform default codepage,
    one undecodable byte kills the drain thread and brings that deadlock back.
    """
    cmd = [ffmpeg_bin(), "-hide_banner", "-nostdin", "-y", "-progress", "pipe:1", "-nostats", *args]
    logger.info("ffmpeg %s", " ".join(args))
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, encoding="utf-8", errors="replace")
    tail = collections.deque(maxlen=60)

    def drain():
        try:
            for line in proc.stdout:
                line = line.rstrip()
                if line.startswith(("out_time_us=", "out_time_ms=")):
                    if progress_cb and duration:
                        try:
                            seconds = int(line.split("=", 1)[1]) / 1_000_000
                            progress_cb(min(max(seconds / duration, 0.0), 1.0))
                        except ValueError:
                            pass
                elif line and not _PROGRESS_KEY_RE.match(line):
                    tail.append(line)
        except Exception:  # noqa: BLE001 - never let draining stop silently
            logger.exception("error draining ffmpeg output")

    reader = threading.Thread(target=drain, daemon=True)
    reader.start()
    while proc.poll() is None:
        if cancel_event is not None and cancel_event.is_set():
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
            reader.join(timeout=2)
            raise Cancelled()
        time.sleep(0.2)
    reader.join(timeout=5)
    if proc.returncode != 0:
        raise MediaError("فشل FFmpeg:\n" + "\n".join(tail))


@functools.lru_cache(maxsize=1)
def nvenc_available() -> bool:
    """Listing h264_nvenc isn't enough (it's listed even with no GPU/driver), so do a
    tiny real encode with the exact arguments used for exports."""
    try:
        ff = ffmpeg_bin()
        encoders = subprocess.run([ff, "-hide_banner", "-encoders"], capture_output=True,
                                  text=True, timeout=30, encoding="utf-8", errors="replace").stdout
        if "h264_nvenc" not in encoders:
            return False
        test = subprocess.run(
            [ff, "-hide_banner", "-nostdin", "-f", "lavfi", "-i", "color=c=black:s=256x256:d=0.2",
             *NVENC_ARGS, "-pix_fmt", "yuv420p", "-f", "null", "-"],
            capture_output=True, timeout=60,
        )
        return test.returncode == 0
    except (MediaError, OSError, subprocess.TimeoutExpired):
        return False


def video_encoder_args(preview: bool = False) -> list[str]:
    if nvenc_available():
        return NVENC_PREVIEW_ARGS if preview else NVENC_ARGS
    return X264_PREVIEW_ARGS if preview else X264_ARGS


def build_cut_args(src: str, start: float, end: float, out: str, mode: str, venc: list[str]) -> list[str]:
    duration = max(end - start, 0.1)
    head = ["-ss", f"{start:.3f}", "-i", src, "-t", f"{duration:.3f}", "-map", "0:v:0", "-map", "0:a:0?"]
    if mode == "fast":
        # Stream copy: near-instant, but the cut snaps to the keyframe before `start`.
        return [*head, "-c", "copy", "-avoid_negative_ts", "make_zero", "-movflags", "+faststart", out]
    return [*head, "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2,setsar=1", *venc,
            "-pix_fmt", "yuv420p", *AUDIO_ARGS, "-movflags", "+faststart", out]


def fit_filter(fit: str, w: int, h: int) -> str:
    if fit == "contain":
        return f"scale={w}:{h}:force_original_aspect_ratio=decrease,setsar=1"
    if fit == "stretch":
        return f"scale={w}:{h},setsar=1"
    return f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1"


def build_template_args(src: str, start: float, end: float, background: str, overlay: str | None,
                        tpl: dict, out: str, venc: list[str], fps: str = "30/1") -> list[str]:
    """Composite: template background -> video (fitted into its rect) -> text overlay.

    Text is rendered by the browser into `overlay` (a transparent PNG), which is what
    makes Arabic shaping come out right - ffmpeg's drawtext is never involved.
    """
    duration = max(end - start, 0.1)
    cw, ch = even(tpl["canvas_w"]), even(tpl["canvas_h"])
    v = tpl["video"]
    rw, rh = max(2, int(v["w"])), max(2, int(v["h"]))
    x, y = int(v["x"]), int(v["y"])
    fit = v.get("fit", "cover")
    pos = f"x={x}+({rw}-w)/2:y={y}+({rh}-h)/2" if fit == "contain" else f"x={x}:y={y}"

    # -ss/-t must sit before the *video's* -i: placed after it they'd bind to the
    # next input (the looped image) and the clip duration would come out wrong.
    # Looped images get the source fps so the output keeps the video's frame rate.
    args = ["-ss", f"{start:.3f}", "-t", f"{duration:.3f}", "-i", src,
            "-loop", "1", "-framerate", fps, "-i", background]
    filters = [
        f"[1:v]scale={cw}:{ch},setsar=1[bg]",
        f"[0:v]{fit_filter(fit, rw, rh)}[vid]",
        f"[bg][vid]overlay={pos}:shortest=1[base]",
    ]
    last = "base"
    if overlay:
        args += ["-loop", "1", "-framerate", fps, "-i", overlay]
        filters += [f"[2:v]scale={cw}:{ch}[txt]", f"[{last}][txt]overlay=0:0:shortest=1[comp]"]
        last = "comp"
    filters.append(f"[{last}]format=yuv420p[vout]")
    return [*args, "-filter_complex", ";".join(filters), "-map", "[vout]", "-map", "0:a:0?",
            *venc, *AUDIO_ARGS, "-movflags", "+faststart", "-shortest", out]


def build_preview_args(src: str, out: str, venc_preview: list[str]) -> list[str]:
    # Short side 360px: light enough to stream through the Colab proxy smoothly.
    vf = "scale='if(gt(iw,ih),-2,360)':'if(gt(iw,ih),360,-2)',setsar=1"
    return ["-i", src, "-map", "0:v:0", "-map", "0:a:0?", "-vf", vf, *venc_preview,
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "64k", "-ac", "1",
            "-movflags", "+faststart", out]


def build_audio_chunks_args(src: str, out_pattern: str, chunk_seconds: int) -> list[str]:
    return ["-i", src, "-vn", "-ac", "1", "-ar", "16000", "-c:a", "aac", "-b:a", "48k",
            "-f", "segment", "-segment_time", str(chunk_seconds), "-segment_format", "adts",
            "-reset_timestamps", "1", out_pattern]
