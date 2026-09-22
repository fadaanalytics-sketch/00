import pytest

from app import config, db
from app.models import Project, Template, TextBox, Topic


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(db, "_conn", None)
    yield
    if db._conn is not None:
        db._conn.close()
    db._conn = None


def _make_project(name="p1"):
    return Project(
        id=None, name=name, source_type="local", source_url="/tmp/x.mp4",
        video_path="/tmp/x.mp4",
    )


def test_create_and_get_project():
    pid = db.create_project(_make_project())
    p = db.get_project(pid)
    assert p.name == "p1"
    assert p.status == "new"


def test_update_project():
    pid = db.create_project(_make_project())
    p = db.get_project(pid)
    p.status = "transcribed"
    p.transcript_json = "[]"
    db.update_project(p)
    reloaded = db.get_project(pid)
    assert reloaded.status == "transcribed"
    assert reloaded.transcript_json == "[]"


def test_delete_project_cascades_topics():
    pid = db.create_project(_make_project())
    db.replace_topics(pid, [
        Topic(id=None, project_id=pid, mode="social_clips", name="t1",
              text="x", start=0, end=1, duration=1),
    ])
    assert len(db.list_topics(pid)) == 1
    db.delete_project(pid)
    assert db.get_project(pid) is None
    assert db.list_topics(pid) == []


def test_list_projects_ordered_newest_first():
    id1 = db.create_project(_make_project("a"))
    id2 = db.create_project(_make_project("b"))
    ids = [p.id for p in db.list_projects()]
    assert ids == [id2, id1]


def test_topic_selection_toggle():
    pid = db.create_project(_make_project())
    db.replace_topics(pid, [
        Topic(id=None, project_id=pid, mode="social_clips", name="t1",
              text="x", start=0, end=1, duration=1, selected=True),
    ])
    topic = db.list_topics(pid)[0]
    db.set_topic_selected(topic.id, False)
    assert db.list_topics(pid)[0].selected is False


def test_template_save_and_roundtrip():
    tpl = Template(
        id=None, name="tpl1", image_path="/tmp/img.png", canvas_w=640, canvas_h=480,
        video_x=10, video_y=20, video_w=300, video_h=200,
        text_boxes=[TextBox(text="hi", x=5, y=5, font_size=20, font_color="#FF0000")],
    )
    tid = db.save_template(tpl)
    reloaded = db.get_template(tid)
    assert reloaded.name == "tpl1"
    assert reloaded.text_boxes[0].text == "hi"
    assert reloaded.text_boxes[0].font_color == "#FF0000"


def test_settings_get_set_roundtrip():
    db.set_setting("api_key", "secret-value")
    assert db.get_setting("api_key") == "secret-value"
    assert db.get_setting("missing_key", "default") == "default"
