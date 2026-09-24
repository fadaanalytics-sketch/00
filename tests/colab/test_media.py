import sys
import threading

import pytest

from ava import media
from ava.errors import Cancelled

from .conftest import make_png, needs_ffmpeg, probe_streams

TPL = {"canvas_w": 1080, "canvas_h": 1920, "video": {"x": 0, "y": 420, "w": 1080, "h": 1080, "fit": "cover"}}


def test_even_rounds_up():
    assert media.even(940) == 940
    assert media.even(941) == 942
    assert media.even(940.6) == 942


def test_cut_args_accurate_forces_even_dimensions():
    args = media.build_cut_args("in.mp4", 1, 4, "out.mp4", "accurate", media.X264_ARGS)
    assert args[args.index("-vf") + 1].startswith("scale=trunc(iw/2)*2:trunc(ih/2)*2")
    assert "libx264" in args and args[-1] == "out.mp4"


def test_cut_args_fast_is_stream_copy():
    args = media.build_cut_args("in.mp4", 1, 4, "out.mp4", "fast", media.X264_ARGS)
    assert args[args.index("-c") + 1] == "copy"
    assert "-vf" not in args and "libx264" not in args


def test_template_args_bind_seek_and_duration_to_the_video_input():
    """Regression (same bug as the desktop app): -ss/-t placed between the two -i
    flags bind to the *image* input and the clip duration comes out wrong."""
    args = media.build_template_args("in.mp4", 2, 5, "bg.png", None, TPL, "out.mp4", media.X264_ARGS)
    video_i = args.index("in.mp4") - 1
    assert args[video_i] == "-i"
    assert args.index("-ss") < video_i and args.index("-t") < video_i
    assert args.index("bg.png") > video_i


def test_template_args_looped_images_use_source_fps_and_even_canvas():
    tpl = dict(TPL, canvas_w=941)
    args = media.build_template_args("in.mp4", 0, 3, "bg.png", "ov.png", tpl, "out.mp4",
                                     media.X264_ARGS, fps="30000/1001")
    assert args.count("-framerate") == 2
    assert args[args.index("-framerate") + 1] == "30000/1001"
    graph = args[args.index("-filter_complex") + 1]
    assert "scale=942:1920" in graph  # odd canvas width rounded up to even
    assert "[2:v]scale=942:1920[txt]" in graph


@pytest.mark.parametrize("fit,expect", [
    ("cover", "force_original_aspect_ratio=increase,crop=1080:1080"),
    ("contain", "force_original_aspect_ratio=decrease"),
    ("stretch", "scale=1080:1080,setsar=1"),
])
def test_fit_modes(fit, expect):
    tpl = dict(TPL, video=dict(TPL["video"], fit=fit))
    graph = media.build_template_args("in.mp4", 0, 3, "bg.png", None, tpl, "o.mp4", media.X264_ARGS)
    graph = graph[graph.index("-filter_complex") + 1]
    assert expect in graph
    if fit == "contain":
        assert "x=0+(1080-w)/2:y=420+(1080-h)/2" in graph


def _run_in_thread(fn, timeout=10):
    result = {}

    def target():
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            result["error"] = e

    t = threading.Thread(target=target, daemon=True)
    t.start()
    t.join(timeout)
    assert not t.is_alive(), "run_ffmpeg deadlocked"
    if "error" in result:
        raise result["error"]


def test_run_ffmpeg_drains_large_output_and_survives_invalid_utf8(monkeypatch):
    """Regression for two desktop-app bugs at once: an undrained pipe deadlocks once
    output passes ~64KB, and one undecodable byte used to kill the drain thread."""
    script = ("import sys\nsys.stdout.buffer.write(bytes([0x81, 0x8d, 0xff]) + b'\\n')\n"
              "for _ in range(3000):\n    print('x' * 200)\n")
    monkeypatch.setattr(media, "ffmpeg_bin", lambda: sys.executable)
    # run_ffmpeg prepends ffmpeg-only flags; make the "ffmpeg" a python that ignores them.
    wrapper = ["-c", f"import sys; exec({script!r})"]
    monkeypatch.setattr(media.subprocess, "Popen", _popen_dropping_ffmpeg_flags(media.subprocess.Popen))
    _run_in_thread(lambda: media.run_ffmpeg(wrapper))


def _popen_dropping_ffmpeg_flags(real_popen):
    def popen(cmd, *a, **kw):
        return real_popen([cmd[0], *cmd[cmd.index("-c"):]], *a, **kw)
    return popen


def test_run_ffmpeg_failure_reports_tail(monkeypatch):
    monkeypatch.setattr(media, "ffmpeg_bin", lambda: sys.executable)
    monkeypatch.setattr(media.subprocess, "Popen", _popen_dropping_ffmpeg_flags(media.subprocess.Popen))
    with pytest.raises(media.MediaError, match="boom-detail"):
        media.run_ffmpeg(["-c", "import sys; print('frame=1'); print('boom-detail'); sys.exit(3)"])


def test_run_ffmpeg_cancel(monkeypatch):
    monkeypatch.setattr(media, "ffmpeg_bin", lambda: sys.executable)
    monkeypatch.setattr(media.subprocess, "Popen", _popen_dropping_ffmpeg_flags(media.subprocess.Popen))
    ev = threading.Event()
    ev.set()
    with pytest.raises(Cancelled):
        media.run_ffmpeg(["-c", "import time; time.sleep(30)"], cancel_event=ev)


@needs_ffmpeg
def test_probe(sample_video):
    info = media.probe(str(sample_video))
    assert (info["width"], info["height"], info["fps"], info["has_audio"]) == (640, 360, "30/1", True)
    assert info["duration"] == pytest.approx(6, abs=0.2)


@needs_ffmpeg
def test_template_export_end_to_end(tmp_path, sample_video):
    bg = make_png(tmp_path / "bg.png", 942, 1672, "purple")
    overlay = make_png(tmp_path / "ov.png", 942, 1672, "white@0.0")
    tpl = {"canvas_w": 941, "canvas_h": 1672,  # the odd width from the real bug report
           "video": {"x": 0, "y": 400, "w": 941, "h": 700, "fit": "contain"}}
    out = tmp_path / "out.mp4"
    progress = []
    media.run_ffmpeg(media.build_template_args(str(sample_video), 1.0, 3.5, str(bg), str(overlay), tpl,
                                               str(out), media.X264_ARGS, fps="30/1"),
                     duration=2.5, progress_cb=progress.append)
    info = probe_streams(out)
    assert (info["width"], info["height"], info["fps"]) == (942, 1672, "30/1")
    assert info["duration"] == pytest.approx(2.5, abs=0.1)
    assert info["has_audio"]
    assert progress and progress[-1] > 0.9


@needs_ffmpeg
def test_accurate_cut_duration(tmp_path, sample_video):
    out = tmp_path / "cut.mp4"
    media.run_ffmpeg(media.build_cut_args(str(sample_video), 1.0, 3.0, str(out), "accurate", media.X264_ARGS))
    assert probe_streams(out)["duration"] == pytest.approx(2.0, abs=0.1)


@needs_ffmpeg
@pytest.mark.parametrize("size,expect", [("1280x720", (640, 360)), ("720x1280", (360, 640))])
def test_preview_short_side_is_360(tmp_path, size, expect):
    src = tmp_path / "src.mp4"
    import subprocess
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
                    "-i", f"testsrc2=size={size}:rate=30:duration=1", str(src)], check=True)
    out = tmp_path / "prev.mp4"
    media.run_ffmpeg(media.build_preview_args(str(src), str(out), media.X264_PREVIEW_ARGS))
    info = probe_streams(out)
    assert (info["width"], info["height"]) == expect


def test_nvenc_falls_back_when_unavailable(monkeypatch):
    monkeypatch.setattr(media, "nvenc_available", lambda: False)
    assert media.video_encoder_args() == media.X264_ARGS
    monkeypatch.setattr(media, "nvenc_available", lambda: True)
    assert media.video_encoder_args() == media.NVENC_ARGS
    assert media.video_encoder_args(preview=True) == media.NVENC_PREVIEW_ARGS
