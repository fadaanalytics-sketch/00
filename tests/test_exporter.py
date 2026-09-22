import shutil
import subprocess

import pytest

from app.exporter import build_cut_cmd, build_template_cmd, cut_clip, export_with_template
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


def test_build_template_cmd_escapes_drawtext_special_chars():
    template = Template(
        id=None, name="t", image_path="template.png", canvas_w=640, canvas_h=480,
        video_x=0, video_y=0, video_w=320, video_h=240,
        text_boxes=[TextBox(text="100%: قيمة", x=0, y=0)],
    )
    cmd = build_template_cmd("ffmpeg", "video.mp4", 0, 1, template, "out.mp4")
    filter_complex = cmd[cmd.index("-filter_complex") + 1]
    assert "100\\%\\: قيمة" in filter_complex


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


def _probe_duration(path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        check=True, capture_output=True, text=True,
    )
    return float(result.stdout.strip())
