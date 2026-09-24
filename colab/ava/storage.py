"""Persistence on Google Drive: projects, templates, settings (plain JSON files).

State lives on Drive rather than the Colab VM so nothing is lost when a session
ends - reopening the notebook picks up every project, transcript and template.
"""
import base64
import binascii
import json
import os
import re
import secrets
import shutil
import threading
import time
import unicodedata
from datetime import datetime, timezone

from . import config
from .errors import NotFound, UserError

_lock = threading.RLock()
_ID_RE = re.compile(r"^[A-Za-z0-9_\-]+$")


def new_id(prefix: str) -> str:
    return f"{prefix}_{time.strftime('%Y%m%d%H%M%S')}_{secrets.token_hex(3)}"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, path)


def decode_data_url(data_url: str) -> tuple[str, bytes]:
    m = re.match(r"^data:([\w/+.-]+);base64,(.*)$", data_url or "", re.DOTALL)
    if not m:
        raise UserError("صيغة الصورة غير صالحة")
    try:
        return m.group(1), base64.b64decode(m.group(2), validate=True)
    except (binascii.Error, ValueError) as e:
        raise UserError("تعذر قراءة الصورة") from e


def safe_filename(name: str, max_len: int = 80) -> str:
    # Combining marks (Arabic tashkeel such as shadda) aren't isalnum(); keep them,
    # otherwise "معدّل" would become "معد_ل".
    keep = "".join(c if c.isalnum() or unicodedata.category(c).startswith("M") or c in "-_" else " "
                   for c in name)
    keep = re.sub(r"\s+", " ", keep).strip(" -_")
    return keep[:max_len].strip() or "clip"


# ---------- Drive paths ----------
# normpath (not realpath) on purpose: Drive shortcuts show up as symlinks into
# /content/drive/.shortcut-targets-by-id, and those must stay usable.

def resolve_drive_path(rel: str) -> str:
    root = os.path.normpath(config.paths().mount_root)
    rel = (rel or "").replace("\\", "/").lstrip("/")
    full = os.path.normpath(os.path.join(root, rel))
    if full != root and not full.startswith(root + os.sep):
        raise UserError("المسار خارج Google Drive")
    return full


def to_drive_rel(full: str) -> str:
    root = os.path.normpath(config.paths().mount_root)
    rel = os.path.relpath(os.path.normpath(full), root)
    return "" if rel == "." else rel.replace(os.sep, "/")


def browse(rel: str) -> dict:
    full = resolve_drive_path(rel)
    if not os.path.isdir(full):
        raise NotFound("الفولدر غير موجود")
    dirs, files = [], []
    with os.scandir(full) as entries:
        for e in entries:
            if e.name.startswith("."):
                continue
            try:
                if e.is_dir():
                    dirs.append({"name": e.name, "path": to_drive_rel(e.path)})
                elif os.path.splitext(e.name)[1].lower() in config.VIDEO_EXTENSIONS:
                    st = e.stat()
                    files.append({"name": e.name, "path": to_drive_rel(e.path),
                                  "size": st.st_size, "modified": st.st_mtime})
            except OSError:
                continue
    dirs.sort(key=lambda d: d["name"].casefold())
    files.sort(key=lambda f: f["name"].casefold())
    path = to_drive_rel(full)
    parent = None if path == "" else to_drive_rel(os.path.dirname(full))
    return {"path": path, "parent": parent, "dirs": dirs, "files": files}


# ---------- projects ----------

def _project_path(pid: str) -> str:
    if not _ID_RE.match(pid or ""):
        raise NotFound("مشروع غير موجود")
    return os.path.join(config.paths().projects, f"{pid}.json")


def project_stage(p: dict) -> str:
    if p.get("exports"):
        return "exported"
    if p.get("topics"):
        return "analyzed"
    if (p.get("transcript") or {}).get("segments"):
        return "transcribed"
    return "new"


def list_projects() -> list[dict]:
    folder = config.paths().projects
    if not os.path.isdir(folder):
        return []
    out = []
    for name in os.listdir(folder):
        if not name.endswith(".json"):
            continue
        p = read_json(os.path.join(folder, name))
        if not p:
            continue
        out.append({"id": p["id"], "name": p["name"], "video": p["video"],
                    "created_at": p.get("created_at", ""), "stage": project_stage(p)})
    out.sort(key=lambda p: p["created_at"], reverse=True)
    return out


def get_project(pid: str) -> dict:
    p = read_json(_project_path(pid))
    if p is None:
        raise NotFound("مشروع غير موجود")
    return p


def save_project(p: dict):
    with _lock:
        p["updated_at"] = now_iso()
        write_json(_project_path(p["id"]), p)


def update_project(pid: str, fn) -> dict:
    """Read-modify-write under a lock: the job thread and API requests both edit projects."""
    with _lock:
        p = get_project(pid)
        fn(p)
        save_project(p)
        return p


def delete_project(pid: str):
    with _lock:
        path = _project_path(pid)
        if not os.path.exists(path):
            raise NotFound("مشروع غير موجود")
        os.remove(path)
        preview = preview_path(pid)
        if os.path.exists(preview):
            os.remove(preview)


def preview_path(pid: str) -> str:
    _project_path(pid)  # validates the id
    return os.path.join(config.paths().previews, f"{pid}.mp4")


# ---------- templates ----------

def _template_dir(tid: str) -> str:
    if not _ID_RE.match(tid or ""):
        raise NotFound("قالب غير موجود")
    return os.path.join(config.paths().templates, tid)


def list_templates() -> list[dict]:
    folder = config.paths().templates
    if not os.path.isdir(folder):
        return []
    out = []
    for name in os.listdir(folder):
        t = read_json(os.path.join(folder, name, "template.json"))
        if t:
            out.append(t)
    out.sort(key=lambda t: t.get("updated_at", ""), reverse=True)
    return out


def get_template(tid: str) -> dict:
    t = read_json(os.path.join(_template_dir(tid), "template.json"))
    if t is None:
        raise NotFound("قالب غير موجود")
    return t


def save_template(tpl: dict, background: bytes | None, background_mime: str | None,
                  source: bytes | None, source_mime: str | None, clear_source: bool = False) -> dict:
    with _lock:
        tid = tpl.get("id") or new_id("tpl")
        folder = _template_dir(tid)
        existing = read_json(os.path.join(folder, "template.json")) or {}
        os.makedirs(folder, exist_ok=True)
        tpl = dict(tpl, id=tid, updated_at=now_iso())
        tpl.setdefault("created_at", existing.get("created_at") or now_iso())

        def put_image(kind, data, mime):
            ext = config.IMAGE_MIME_EXT.get(mime)
            if not ext:
                raise UserError("نوع الصورة غير مدعوم (PNG أو JPG أو WEBP فقط)")
            old = existing.get(f"{kind}_file")
            if old and os.path.exists(os.path.join(folder, old)):
                os.remove(os.path.join(folder, old))
            fname = f"{kind}{ext}"
            with open(os.path.join(folder, fname), "wb") as f:
                f.write(data)
            return fname

        tpl["background_file"] = existing.get("background_file")
        tpl["source_file"] = existing.get("source_file")
        if background is not None:
            tpl["background_file"] = put_image("background", background, background_mime)
        if clear_source and tpl["source_file"]:
            os.remove(os.path.join(folder, tpl["source_file"]))
            tpl["source_file"] = None
        if source is not None:
            tpl["source_file"] = put_image("source", source, source_mime)
        if not tpl["background_file"]:
            raise UserError("القالب يحتاج صورة خلفية مُجهّزة")
        write_json(os.path.join(folder, "template.json"), tpl)
        return tpl


def template_file(tid: str, kind: str) -> str:
    t = get_template(tid)
    fname = t.get(f"{kind}_file")
    if not fname:
        raise NotFound("الصورة غير موجودة")
    path = os.path.join(_template_dir(tid), fname)
    if not os.path.exists(path):
        raise NotFound("الصورة غير موجودة")
    return path


def delete_template(tid: str):
    with _lock:
        folder = _template_dir(tid)
        if not os.path.isdir(folder):
            raise NotFound("قالب غير موجود")
        shutil.rmtree(folder)


# ---------- settings ----------

def get_settings() -> dict:
    s = dict(config.DEFAULT_SETTINGS)
    s.update(read_json(config.paths().settings, {}) or {})
    return s


def save_settings(new: dict) -> dict:
    with _lock:
        merged = get_settings()
        merged.update({k: v for k, v in new.items() if k in config.DEFAULT_SETTINGS})
        write_json(config.paths().settings, merged)
        return merged
