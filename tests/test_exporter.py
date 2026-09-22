import shutil
import subprocess
import sys
import threading

import pytest

from app.exporter import (
    _even, _run, build_cut_cmd, build_template_cmd, cut_clip, export_with_template,
)
from app.models import Template, TextBox

FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None


def test_build_cut_cmd_seeks_and_trims_the_single_input():
    cmd = build_cut_cmd("ffmpeg", "video.mp4", 1.0, 3.5, "out.mp4")
    assert cmd[0] == "ffmpeg"
    assert "-i" in cmd
    i_idx = cmd.index("-i")
    assert cmd[i_idx + 1] == "video.mp4"
    assert cmd[-1] == "out.mp4"


def test_build_template_cmd_applies_ss_and_t_to_the_video_input_not_the_image():
    """Regression test: -ss/-t must precede the VIDEO's -i, not the template image's -i.

    Placing them between the two -i flags makes ffmpeg silently attach them to the
    *next* input (the template image) instead of the video, producing clips with the
    wrong duration.
    """
    template = Template(
        id=None, name="t", image_path="template.png", canvas_w=640, canvas_h=480,
        video_x=0, video_y=0, video_w=320, video_h=240, text_boxes=[],
    )
    cmd = build_template_cmd("ffmpeg", "video.mp4", 1.0, 3.5, template, "out.mp4")

    video_i_idx = cmd.index("video.mp4") - 1
    assert cmd[video_i_idx] == "-i"

    ss_idx = cmd.index("-ss")
    t_idx = cmd.index("-t")
    image_i_idx = cmd.index("template.png") - 1

    # -ss and -t must come BEFORE the video's own -i ...
    assert ss_idx < video_i_idx
    assert t_idx < video_i_idx
    # ... and therefore before the template image's -i too.
    assert video_i_idx < image_i_idx


def test_even_helper():
    assert _even(940) == 940
    assert _even(941) == 942


def test_build_cut_cmd_forces_even_output_dimensions():
    """Regression test: libx264 (yuv420p) rejects odd width/height outright with
    'width not divisible by 2'. A source video with an odd dimension (uncommon
    but real, e.g. some screen recordings) must not make export fail."""
    cmd = build_cut_cmd("ffmpeg", "video.mp4", 0, 1, "out.mp4")
    assert "-vf" in cmd
    vf_value = cmd[cmd.index("-vf") + 1]
    assert "trunc(iw/2)*2" in vf_value
    assert "trunc(ih/2)*2" in vf_value


def test_build_template_cmd_rounds_odd_canvas_and_video_dimensions_to_even():
    """Regression test for a real reported failure: a 941x1672 uploaded template
    image (odd width) made ffmpeg fail with 'width not divisible by 2', because
    the final encoded frame is the canvas size, not the source video's size."""
    template = Template(
        id=None, name="t", image_path="template.png", canvas_w=941, canvas_h=1672,
        video_x=0, video_y=0, video_w=301, video_h=201, text_boxes=[],
    )
    cmd = build_template_cmd("ffmpeg", "video.mp4", 0, 1, template, "out.mp4")
    filter_complex = cmd[cmd.index("-filter_complex") + 1]
    assert "scale=942:1672" in filter_complex
    assert "scale=302:202" in filter_complex


def test_build_template_cmd_escapes_drawtext_special_chars():
    template = Template(
        id=None, name="t", image_path="template.png", canvas_w=640, canvas_h=480,
        video_x=0, video_y=0, video_w=320, video_h=240,
        text_boxes=[TextBox(text="100%: قيمة", x=0, y=0)],
    )
    cmd = build_template_cmd("ffmpeg", "video.mp4", 0, 1, template, "out.mp4")
    filter_complex = cmd[cmd.index("-filter_complex") + 1]
    assert "100\\%\\: قيمة" in filter_complex


def test_run_drains_output_instead_of_deadlocking_on_a_full_pipe():
    """Regression test for a real deadlock: ffmpeg writes a steady stream of
    progress output: on a real (non-trivial-length) clip this exceeds the OS
    pipe buffer (~64KB). If nothing reads the pipe while the process runs,
    the child blocks on write() forever and _run() never returns, leaving a
    partially-written, unplayable output file behind. Tiny test clips never
    produce enough output to hit this, so this test forces >64KB of output
    directly instead of depending on ffmpeg/clip length.
    """
    big_output_cmd = [
        sys.executable, "-c",
        "import sys\nfor _ in range(3000):\n    sys.stdout.write('x' * 200 + chr(10))",
    ]
    result = {}

    def target():
        try:
            _run(big_output_cmd)
        except Exception as e:  # noqa: BLE001 - re-raised on the test thread below
            result["error"] = e

    # A daemon thread: if _run() really deadlocks, this thread is abandoned
    # rather than hanging the whole test process waiting for it to finish.
    t = threading.Thread(target=target, daemon=True)
    t.start()
    t.join(timeout=10)
    assert not t.is_alive(), "_run() deadlocked on a full stdout pipe (regression!)"
    if "error" in result:
        raise result["error"]


def test_run_tolerates_non_utf8_bytes_in_ffmpeg_output():
    """Regression test: on Windows, Python's text=True defaults to the system's
    ANSI codepage (e.g. cp1252) unless an encoding is given explicitly. ffmpeg's
    console output isn't guaranteed to be valid in that codepage (or even valid
    UTF-8), so decoding it crashed the draining thread with UnicodeDecodeError.
    That crash is silent from _run()'s point of view (it happens on a
    background thread) but stops draining right there - so on a real
    (non-trivial-length) ffmpeg run, any output produced *after* the bad bytes
    would refill the pipe with nobody left to drain it, reintroducing the
    exact deadlock this module exists to avoid. Write invalid bytes followed
    by enough additional output to overflow the OS pipe buffer, and require
    that all of it is still drained (proving draining survived past the bad
    bytes, not just that _run() itself didn't crash).
    """
    invalid_bytes_then_lots_more_cmd = [
        sys.executable, "-c",
        "import sys\n"
        "sys.stdout.buffer.write(bytes([0x81, 0x8d, 0xff]))\n"
        "sys.stdout.buffer.flush()\n"
        "for _ in range(3000):\n"
        "    sys.stdout.write('x' * 200 + chr(10))\n",
    ]
    result = {}

    def target():
        try:
            _run(invalid_bytes_then_lots_more_cmd)
        except Exception as e:  # noqa: BLE001 - re-raised on the test thread below
            result["error"] = e

    t = threading.Thread(target=target, daemon=True)
    t.start()
    t.join(timeout=10)
    assert not t.is_alive(), "draining stopped after the bad bytes and _run() deadlocked"
    if "error" in result:
        raise result["error"]


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg not installed")
def test_cut_clip_produces_correct_duration(tmp_path):
    video = tmp_path / "test.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=15:duration=5",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=5", "-shortest", str(video)],
        check=True, capture_output=True,
    )
    out = tmp_path / "out.mp4"
    cut_clip(str(video), 0.5, 2.5, str(out))
    duration = _probe_duration(out)
    assert duration == pytest.approx(2.0, abs=0.1)


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg not installed")
def test_export_with_template_produces_correct_duration(tmp_path):
    video = tmp_path / "test.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=15:duration=5",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=5", "-shortest", str(video)],
        check=True, capture_output=True,
    )
    template_img = tmp_path / "template.png"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=blue:size=640x480",
         "-frames:v", "1", str(template_img)],
        check=True, capture_output=True,
    )
    template = Template(
        id=None, name="t", image_path=str(template_img), canvas_w=640, canvas_h=480,
        video_x=50, video_y=50, video_w=320, video_h=240,
        text_boxes=[TextBox(text="اختبار", x=10, y=10)],
    )
    out = tmp_path / "out.mp4"
    export_with_template(str(video), 0.5, 2.5, template, str(out))
    duration = _probe_duration(out)
    assert duration == pytest.approx(2.0, abs=0.1)


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg not installed")
def test_export_with_template_succeeds_with_odd_sized_template_image(tmp_path):
    """End-to-end regression test for the exact reported failure: exporting with
    a template whose image has an odd width (941x1672 in the real report) used
    to fail outright with ffmpeg's "width not divisible by 2" libx264 error."""
    video = tmp_path / "test.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=15:duration=2",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=2", "-shortest", str(video)],
        check=True, capture_output=True,
    )
    template_img = tmp_path / "template.png"
    subprocess.run(
        # Odd width, same as the reported 941x1672 template (scaled down for a fast test).
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=blue:size=471x836",
         "-frames:v", "1", str(template_img)],
        check=True, capture_output=True,
    )
    template = Template(
        id=None, name="t", image_path=str(template_img), canvas_w=471, canvas_h=836,
        video_x=0, video_y=0, video_w=471, video_h=627, text_boxes=[],
    )
    out = tmp_path / "out.mp4"
    export_with_template(str(video), 0, 1, template, str(out))  # must not raise ExportError
    assert out.stat().st_size > 0


def _probe_duration(path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        check=True, capture_output=True, text=True,
    )
    return float(result.stdout.strip())
