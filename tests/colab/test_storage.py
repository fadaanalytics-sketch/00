import pytest

from ava import storage
from ava.errors import NotFound, UserError


def test_resolve_drive_path_blocks_traversal(drive):
    assert storage.resolve_drive_path("AIVideoAnalyzer/videos") == str(drive / "AIVideoAnalyzer" / "videos")
    assert storage.resolve_drive_path("") == str(drive)
    for bad in ("../etc", "AIVideoAnalyzer/../../x", "/../../root"):
        with pytest.raises(UserError):
            storage.resolve_drive_path(bad)


def test_browse_lists_folders_and_videos_only(drive):
    videos = drive / "AIVideoAnalyzer" / "videos"
    (videos / "مجلد").mkdir()
    (videos / "a.mp4").write_bytes(b"x")
    (videos / "b.MOV").write_bytes(b"x")
    (videos / "notes.txt").write_text("x")
    (videos / ".hidden.mp4").write_bytes(b"x")
    result = storage.browse("AIVideoAnalyzer/videos")
    assert [d["name"] for d in result["dirs"]] == ["مجلد"]
    assert [f["name"] for f in result["files"]] == ["a.mp4", "b.MOV"]
    assert result["parent"] == "AIVideoAnalyzer"
    assert storage.browse("")["parent"] is None
    with pytest.raises(NotFound):
        storage.browse("nope")


@pytest.mark.parametrize("name,expected", [
    ("يعني إيه تعلم آلي؟ (معدّل)", "يعني إيه تعلم آلي معدّل"),  # shadda kept
    ("a/b\\c:d", "a b c d"),
    ("...", "clip"),
    ("", "clip"),
])
def test_safe_filename(name, expected):
    assert storage.safe_filename(name) == expected


def test_project_crud_and_stage(drive):
    p = {"id": storage.new_id("p"), "name": "x", "video": "v.mp4", "created_at": storage.now_iso(),
         "transcript": None, "topics": [], "exports": []}
    storage.save_project(p)
    assert storage.list_projects()[0]["stage"] == "new"
    storage.update_project(p["id"], lambda pr: pr.update(transcript={"segments": [{"start": 0, "end": 1, "text": "a"}]}))
    assert storage.list_projects()[0]["stage"] == "transcribed"
    storage.update_project(p["id"], lambda pr: pr.update(topics=[{"id": "t"}]))
    assert storage.get_project(p["id"])["topics"] == [{"id": "t"}]
    storage.delete_project(p["id"])
    with pytest.raises(NotFound):
        storage.get_project(p["id"])


def test_project_ids_are_validated(drive):
    with pytest.raises(NotFound):
        storage.get_project("../../etc/passwd")


def test_template_images_replace_and_clear(drive):
    tpl = {"name": "t", "canvas_w": 1080, "canvas_h": 1920, "video": {"x": 0, "y": 0, "w": 10, "h": 10}}
    saved = storage.save_template(tpl, b"JPG1", "image/jpeg", b"PNG1", "image/png")
    tid = saved["id"]
    assert open(storage.template_file(tid, "background"), "rb").read() == b"JPG1"
    assert open(storage.template_file(tid, "source"), "rb").read() == b"PNG1"
    saved = storage.save_template(dict(saved, name="t2"), None, None, None, None, clear_source=True)
    assert saved["name"] == "t2" and saved["background_file"] == "background.jpg" and saved["source_file"] is None
    with pytest.raises(NotFound):
        storage.template_file(tid, "source")
    with pytest.raises(UserError):
        storage.save_template({"name": "no-bg"}, None, None, None, None)
    with pytest.raises(UserError):
        storage.save_template({"name": "gif"}, b"x", "image/gif", None, None)
    storage.delete_template(tid)
    assert storage.list_templates() == []


def test_decode_data_url():
    assert storage.decode_data_url("data:image/png;base64,aGk=") == ("image/png", b"hi")
    with pytest.raises(UserError):
        storage.decode_data_url("not a data url")


def test_settings_defaults_and_unknown_keys_ignored(drive):
    assert storage.get_settings()["analysis_provider"] == "gemini"
    s = storage.save_settings({"analysis_provider": "openrouter", "evil": 1})
    assert s["analysis_provider"] == "openrouter" and "evil" not in s
    assert storage.get_settings()["analysis_provider"] == "openrouter"
