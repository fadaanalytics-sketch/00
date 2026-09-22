"""SQLite persistence layer: projects, topics, templates, settings."""
import json
import sqlite3
from datetime import datetime
from typing import Optional

from . import config
from .models import Project, Topic, Template, TextBox

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_url TEXT,
    video_path TEXT,
    whisper_model TEXT DEFAULT 'small',
    transcript_json TEXT DEFAULT '',
    status TEXT DEFAULT 'new',
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS topics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    mode TEXT,
    name TEXT,
    text TEXT,
    start REAL,
    end REAL,
    duration REAL,
    selected INTEGER DEFAULT 1,
    order_index INTEGER DEFAULT 0,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    image_path TEXT,
    canvas_w INTEGER,
    canvas_h INTEGER,
    video_x INTEGER,
    video_y INTEGER,
    video_w INTEGER,
    video_h INTEGER,
    text_boxes_json TEXT DEFAULT '[]'
);
"""

_conn: Optional[sqlite3.Connection] = None


def get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        config.ensure_dirs()
        _conn = sqlite3.connect(config.DB_PATH)
        _conn.execute("PRAGMA foreign_keys = ON")
        _conn.row_factory = sqlite3.Row
        _conn.executescript(SCHEMA)
        _conn.commit()
    return _conn


# ---------- settings ----------

def get_setting(key: str, default=None):
    row = get_conn().execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    if row is None:
        return default
    try:
        return json.loads(row["value"])
    except (json.JSONDecodeError, TypeError):
        return row["value"]


def set_setting(key: str, value):
    conn = get_conn()
    conn.execute(
        "INSERT INTO settings(key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, json.dumps(value)),
    )
    conn.commit()


# ---------- projects ----------

def create_project(p: Project) -> int:
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO projects (name, source_type, source_url, video_path, whisper_model, "
        "transcript_json, status, created_at) VALUES (?,?,?,?,?,?,?,?)",
        (p.name, p.source_type, p.source_url, p.video_path, p.whisper_model,
         p.transcript_json, p.status, datetime.now().isoformat()),
    )
    conn.commit()
    return cur.lastrowid


def update_project(p: Project):
    conn = get_conn()
    conn.execute(
        "UPDATE projects SET name=?, source_type=?, source_url=?, video_path=?, "
        "whisper_model=?, transcript_json=?, status=? WHERE id=?",
        (p.name, p.source_type, p.source_url, p.video_path, p.whisper_model,
         p.transcript_json, p.status, p.id),
    )
    conn.commit()


def delete_project(project_id: int):
    conn = get_conn()
    conn.execute("DELETE FROM projects WHERE id=?", (project_id,))
    conn.commit()


def list_projects() -> list[Project]:
    rows = get_conn().execute("SELECT * FROM projects ORDER BY id DESC").fetchall()
    return [_row_to_project(r) for r in rows]


def get_project(project_id: int) -> Optional[Project]:
    row = get_conn().execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
    return _row_to_project(row) if row else None


def _row_to_project(row) -> Project:
    return Project(
        id=row["id"], name=row["name"], source_type=row["source_type"],
        source_url=row["source_url"], video_path=row["video_path"],
        whisper_model=row["whisper_model"], transcript_json=row["transcript_json"],
        status=row["status"], created_at=row["created_at"],
    )


# ---------- topics ----------

def replace_topics(project_id: int, topics: list[Topic]):
    conn = get_conn()
    conn.execute("DELETE FROM topics WHERE project_id=?", (project_id,))
    for t in topics:
        conn.execute(
            "INSERT INTO topics (project_id, mode, name, text, start, end, duration, "
            "selected, order_index) VALUES (?,?,?,?,?,?,?,?,?)",
            (project_id, t.mode, t.name, t.text, t.start, t.end, t.duration,
             int(t.selected), t.order_index),
        )
    conn.commit()


def set_topic_selected(topic_id: int, selected: bool):
    conn = get_conn()
    conn.execute("UPDATE topics SET selected=? WHERE id=?", (int(selected), topic_id))
    conn.commit()


def list_topics(project_id: int) -> list[Topic]:
    rows = get_conn().execute(
        "SELECT * FROM topics WHERE project_id=? ORDER BY order_index", (project_id,)
    ).fetchall()
    return [
        Topic(id=r["id"], project_id=r["project_id"], mode=r["mode"], name=r["name"],
              text=r["text"], start=r["start"], end=r["end"], duration=r["duration"],
              selected=bool(r["selected"]), order_index=r["order_index"])
        for r in rows
    ]


# ---------- templates ----------

def save_template(t: Template) -> int:
    conn = get_conn()
    boxes_json = json.dumps([tb.__dict__ for tb in t.text_boxes])
    if t.id is None:
        cur = conn.execute(
            "INSERT INTO templates (name, image_path, canvas_w, canvas_h, video_x, video_y, "
            "video_w, video_h, text_boxes_json) VALUES (?,?,?,?,?,?,?,?,?)",
            (t.name, t.image_path, t.canvas_w, t.canvas_h, t.video_x, t.video_y,
             t.video_w, t.video_h, boxes_json),
        )
        conn.commit()
        return cur.lastrowid
    else:
        conn.execute(
            "UPDATE templates SET name=?, image_path=?, canvas_w=?, canvas_h=?, video_x=?, "
            "video_y=?, video_w=?, video_h=?, text_boxes_json=? WHERE id=?",
            (t.name, t.image_path, t.canvas_w, t.canvas_h, t.video_x, t.video_y,
             t.video_w, t.video_h, boxes_json, t.id),
        )
        conn.commit()
        return t.id


def delete_template(template_id: int):
    conn = get_conn()
    conn.execute("DELETE FROM templates WHERE id=?", (template_id,))
    conn.commit()


def list_templates() -> list[Template]:
    rows = get_conn().execute("SELECT * FROM templates ORDER BY id DESC").fetchall()
    return [_row_to_template(r) for r in rows]


def get_template(template_id: int) -> Optional[Template]:
    row = get_conn().execute("SELECT * FROM templates WHERE id=?", (template_id,)).fetchone()
    return _row_to_template(row) if row else None


def _row_to_template(row) -> Template:
    boxes = [TextBox(**b) for b in json.loads(row["text_boxes_json"] or "[]")]
    return Template(
        id=row["id"], name=row["name"], image_path=row["image_path"],
        canvas_w=row["canvas_w"], canvas_h=row["canvas_h"],
        video_x=row["video_x"], video_y=row["video_y"],
        video_w=row["video_w"], video_h=row["video_h"], text_boxes=boxes,
    )
