"""HTTP API + static UI. Runs inside the Colab VM and is opened in the browser via
Colab's authenticated port proxy (no public URL, no tunnel)."""
import logging
import os
import re
import threading
import urllib.parse
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import analysis, config, media, storage, tasks, transcribe
from .errors import NotFound, UserError
from .jobs import JobManager

logger = logging.getLogger(__name__)
WEB_DIR = os.path.join(os.path.dirname(__file__), "web")
jobs = JobManager()


@asynccontextmanager
async def lifespan(_app):
    config.ensure_dirs()
    # Warm up the slow-ish probes so the first /api/status is instant.
    threading.Thread(target=lambda: (media.nvenc_available(), transcribe.gpu_name()), daemon=True).start()
    yield


app = FastAPI(title="AI Video Analyzer", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


@app.exception_handler(NotFound)
async def _not_found(_req, exc):
    return JSONResponse(status_code=404, content={"detail": str(exc) or "غير موجود"})


@app.exception_handler(UserError)
async def _user_error(_req, exc):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(media.MediaError)
async def _media_error(_req, exc):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


# ---------- models ----------

class CreateProjectReq(BaseModel):
    video: str
    name: str | None = None


class TranscribeReq(BaseModel):
    engine: str = "auto"
    model: str = "auto"
    language: str = ""


class AnalyzeReq(BaseModel):
    mode: str = "social_clips"
    provider: str | None = None
    model: str | None = None


class TopicsReq(BaseModel):
    topics: list[dict]


class ExportReq(BaseModel):
    topic_ids: list[str]
    template_id: str | None = None
    overlays: dict[str, str] = Field(default_factory=dict)
    cut_mode: str = "accurate"
    folder: str | None = None


class TemplateReq(BaseModel):
    template: dict
    background: str | None = None
    source_image: str | None = None
    clear_source: bool = False


class SettingsReq(BaseModel):
    settings: dict


# ---------- helpers ----------

def _ranged_file(path: str, request: Request, media_type: str, download_name: str | None = None):
    """File response with HTTP Range support (needed for seeking in <video>)."""
    size = os.path.getsize(path)
    headers = {"Accept-Ranges": "bytes"}
    if download_name:
        headers["Content-Disposition"] = f"attachment; filename*=UTF-8''{urllib.parse.quote(download_name)}"
    range_header = request.headers.get("range")
    m = re.match(r"^bytes=(\d*)-(\d*)$", range_header or "")
    if not m or (not m.group(1) and not m.group(2)):
        return FileResponse(path, media_type=media_type, headers=headers)
    if m.group(1):
        start = int(m.group(1))
        end = min(int(m.group(2)) if m.group(2) else size - 1, size - 1)
    else:
        start, end = max(0, size - int(m.group(2))), size - 1
    if start >= size or start > end:
        return Response(status_code=416, headers={"Content-Range": f"bytes */{size}"})

    def chunks():
        with open(path, "rb") as f:
            f.seek(start)
            remaining = end - start + 1
            while remaining > 0:
                data = f.read(min(1 << 20, remaining))
                if not data:
                    break
                remaining -= len(data)
                yield data

    headers.update({"Content-Range": f"bytes {start}-{end}/{size}", "Content-Length": str(end - start + 1)})
    return StreamingResponse(chunks(), status_code=206, media_type=media_type, headers=headers)


def _project_payload(p: dict) -> dict:
    preview = storage.preview_path(p["id"])
    has_preview = os.path.exists(preview)
    return dict(p, stage=storage.project_stage(p), has_preview=has_preview,
                preview_version=int(os.path.getmtime(preview)) if has_preview else 0)


def _submit(kind: str, pid: str, fn):
    storage.get_project(pid)  # 404 early
    return jobs.submit(kind, pid, fn).to_dict()


# ---------- pages ----------

@app.get("/")
def index():
    return FileResponse(os.path.join(WEB_DIR, "index.html"), headers={"Cache-Control": "no-store"})


@app.get("/api/status")
def status():
    p = config.paths()
    return {
        "gpu": transcribe.gpu_name(),
        "cuda": transcribe.cuda_available(),
        "nvenc": media.nvenc_available(),
        "gemini_key": bool(config.gemini_key()),
        "openrouter_key": bool(config.openrouter_key()),
        "data_root": storage.to_drive_rel(p.data_root),
        "videos_dir": storage.to_drive_rel(p.videos),
        "whisper_default": transcribe.resolve_model("auto"),
        "whisper_models": config.WHISPER_MODELS,
        "languages": transcribe.LANGUAGES,
    }


@app.get("/api/browse")
def browse(path: str = ""):
    return storage.browse(path)


@app.get("/api/settings")
def get_settings():
    return storage.get_settings()


@app.put("/api/settings")
def put_settings(req: SettingsReq):
    return storage.save_settings(req.settings)


# ---------- projects ----------

@app.get("/api/projects")
def list_projects():
    return storage.list_projects()


@app.post("/api/projects")
def create_project(req: CreateProjectReq):
    full = storage.resolve_drive_path(req.video)
    if not os.path.isfile(full):
        raise UserError("ملف الفيديو غير موجود")
    if os.path.splitext(full)[1].lower() not in config.VIDEO_EXTENSIONS:
        raise UserError("هذا الملف ليس فيديو مدعومًا")
    info = media.probe(full)
    name = (req.name or "").strip() or os.path.splitext(os.path.basename(full))[0]
    project = {"id": storage.new_id("p"), "name": name, "video": storage.to_drive_rel(full),
               "media": info, "created_at": storage.now_iso(), "transcript": None,
               "topics": [], "exports": []}
    storage.save_project(project)
    return _project_payload(project)


@app.get("/api/projects/{pid}")
def get_project(pid: str):
    return _project_payload(storage.get_project(pid))


@app.delete("/api/projects/{pid}")
def delete_project(pid: str):
    storage.delete_project(pid)
    return {"ok": True}


@app.put("/api/projects/{pid}/topics")
def put_topics(pid: str, req: TopicsReq):
    def apply(p):
        p["topics"] = analysis.clean_topics(req.topics, (p.get("media") or {}).get("duration") or 0)
    return {"topics": storage.update_project(pid, apply)["topics"]}


@app.post("/api/projects/{pid}/transcribe")
def start_transcription(pid: str, req: TranscribeReq):
    if req.model not in ("auto", *config.WHISPER_MODELS):
        raise UserError("نموذج Whisper غير معروف")
    return _submit("transcribe", pid,
                   lambda job: tasks.transcription_task(job, pid, req.engine, req.model, req.language))


@app.post("/api/projects/{pid}/analyze")
def start_analysis(pid: str, req: AnalyzeReq):
    if req.mode not in config.ANALYSIS_MODES:
        raise UserError("نمط تحليل غير مدعوم")
    return _submit("analyze", pid,
                   lambda job: tasks.analysis_task(job, pid, req.mode, req.provider, req.model))


@app.post("/api/projects/{pid}/preview")
def start_preview(pid: str):
    return _submit("preview", pid, lambda job: tasks.preview_task(job, pid))


@app.get("/api/projects/{pid}/preview")
def get_preview(pid: str, request: Request):
    path = storage.preview_path(pid)
    if not os.path.exists(path):
        raise NotFound("لا توجد معاينة بعد")
    return _ranged_file(path, request, "video/mp4")


@app.post("/api/projects/{pid}/export")
def start_export(pid: str, req: ExportReq):
    if req.cut_mode not in config.CUT_MODES:
        raise UserError("طريقة قص غير معروفة")
    if req.template_id:
        storage.get_template(req.template_id)
    return _submit("export", pid, lambda job: tasks.export_task(
        job, pid, req.topic_ids, req.template_id, req.overlays, req.cut_mode, req.folder))


# ---------- jobs ----------

@app.get("/api/jobs")
def list_jobs(project_id: str | None = None, active: bool = False):
    return [j.to_dict() for j in jobs.list(project_id, active_only=active)]


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise NotFound("العملية غير موجودة (ربما أُعيد تشغيل الجلسة)")
    return job.to_dict()


@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: str):
    job = jobs.cancel(job_id)
    if not job:
        raise NotFound("العملية غير موجودة")
    return job.to_dict()


# ---------- templates ----------

@app.get("/api/templates")
def list_templates():
    return storage.list_templates()


@app.get("/api/templates/{tid}")
def get_template(tid: str):
    return storage.get_template(tid)


@app.post("/api/templates")
def save_template(req: TemplateReq):
    tpl = req.template
    for key in ("canvas_w", "canvas_h"):
        if not isinstance(tpl.get(key), (int, float)) or not 64 <= tpl[key] <= 4096:
            raise UserError("مقاس القالب غير صالح (من 64 إلى 4096 بكسل)")
    tpl["canvas_w"], tpl["canvas_h"] = media.even(tpl["canvas_w"]), media.even(tpl["canvas_h"])
    video = tpl.get("video")
    if not isinstance(video, dict) or not all(isinstance(video.get(k), (int, float)) for k in "xywh"):
        raise UserError("مكان الفيديو داخل القالب غير صالح")
    if video["w"] < 16 or video["h"] < 16:
        raise UserError("مساحة الفيديو داخل القالب صغيرة جدًا")
    video["fit"] = video.get("fit") if video.get("fit") in ("cover", "contain", "stretch") else "cover"
    if not isinstance(tpl.get("texts", []), list):
        raise UserError("نصوص القالب غير صالحة")
    if not str(tpl.get("name") or "").strip():
        raise UserError("اكتب اسمًا للقالب")
    bg_mime, bg = storage.decode_data_url(req.background) if req.background else (None, None)
    src_mime, src = storage.decode_data_url(req.source_image) if req.source_image else (None, None)
    return storage.save_template(tpl, bg, bg_mime, src, src_mime, clear_source=req.clear_source)


@app.delete("/api/templates/{tid}")
def delete_template(tid: str):
    storage.delete_template(tid)
    return {"ok": True}


@app.get("/api/templates/{tid}/{kind}")
def template_image(tid: str, kind: str):
    if kind not in ("background", "source"):
        raise NotFound("غير موجود")
    return FileResponse(storage.template_file(tid, kind), headers={"Cache-Control": "no-store"})


# ---------- files ----------

@app.get("/api/files")
def download_file(path: str, request: Request):
    full = storage.resolve_drive_path(path)
    if not os.path.isfile(full):
        raise NotFound("الملف غير موجود")
    return _ranged_file(full, request, "video/mp4", download_name=os.path.basename(full))
