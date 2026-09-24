"""The long-running pipelines, each executed on the job worker thread."""
import os
import shutil

from . import analysis, config, llm, media, storage, transcribe
from .errors import UserError


def _video_path(project: dict) -> str:
    path = storage.resolve_drive_path(project["video"])
    if not os.path.isfile(path):
        raise UserError(f"ملف الفيديو غير موجود على الدرايف: {project['video']}")
    return path


def resolve_engine(engine: str) -> str:
    if engine in ("whisper", "gemini"):
        return engine
    if transcribe.cuda_available() or not config.gemini_key():
        return "whisper"
    return "gemini"


def transcription_task(job, pid: str, engine: str, model: str, language: str) -> dict:
    project = storage.get_project(pid)
    video = _video_path(project)
    engine = resolve_engine(engine)
    settings = storage.get_settings()
    progress = lambda p: job.update(progress=p)  # noqa: E731
    status = lambda m: job.update(message=m)  # noqa: E731
    if engine == "gemini":
        transcript = llm.gemini_transcribe(video, settings["gemini_model"], language,
                                           transcribe.LANGUAGES, progress, status, job.cancel_event)
    else:
        transcript = transcribe.transcribe_whisper(video, transcribe.resolve_model(model), language,
                                                   progress, status, job.cancel_event)
    if not transcript["segments"]:
        raise UserError("لم يتم التعرف على أي كلام في الفيديو")
    storage.update_project(pid, lambda p: p.update(transcript=transcript))
    return {"segments": len(transcript["segments"]), "engine": engine}


def analysis_task(job, pid: str, mode: str, provider: str | None, model: str | None) -> dict:
    project = storage.get_project(pid)
    segments = (project.get("transcript") or {}).get("segments") or []
    prompt = analysis.build_prompt(mode, segments)
    settings = storage.get_settings()
    provider = provider or settings["analysis_provider"]
    model = model or settings["openrouter_model" if provider == "openrouter" else "gemini_model"]
    job.update(message=f"جارٍ التحليل عبر {'OpenRouter' if provider == 'openrouter' else 'Gemini'}...")
    raw = llm.generate_text(provider, model, prompt)
    job.check_cancel()
    duration = (project.get("media") or {}).get("duration") or 0
    topics = analysis.parse_topics(raw, duration)
    if not topics:
        raise UserError("لم يقترح الذكاء الاصطناعي أي مقاطع - جرّب مرة أخرى أو غيّر نمط التحليل")
    if settings.get("snap_to_words", True):
        analysis.snap_topics_to_words(topics, segments, duration)

    def apply(p):
        p["topics"] = topics
        p["analysis"] = {"mode": mode, "provider": provider, "model": model, "at": storage.now_iso()}
    storage.update_project(pid, apply)
    return {"topics": len(topics)}


def preview_task(job, pid: str) -> dict:
    project = storage.get_project(pid)
    video = _video_path(project)
    duration = (project.get("media") or {}).get("duration") or None
    tmp = os.path.join(config.paths().work, f"{job.id}_preview.mp4")
    try:
        job.update(message="جارٍ تجهيز نسخة معاينة خفيفة...")
        media.run_ffmpeg(media.build_preview_args(video, tmp, media.video_encoder_args(preview=True)),
                         duration=duration, progress_cb=lambda p: job.update(progress=p * 0.95),
                         cancel_event=job.cancel_event)
        job.update(message="جارٍ حفظ المعاينة على الدرايف...")
        shutil.copyfile(tmp, storage.preview_path(pid))
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    return {"ok": True}


def _unique_path(folder: str, filename: str) -> str:
    base, ext = os.path.splitext(filename)
    candidate, n = os.path.join(folder, filename), 2
    while os.path.exists(candidate):
        candidate = os.path.join(folder, f"{base}_{n}{ext}")
        n += 1
    return candidate


def export_task(job, pid: str, topic_ids: list[str], template_id: str | None,
                overlays: dict[str, str], cut_mode: str, folder: str | None) -> dict:
    project = storage.get_project(pid)
    video = _video_path(project)
    wanted = set(topic_ids)
    clips = [t for t in project.get("topics") or [] if t["id"] in wanted]
    if not clips:
        raise UserError("لم يتم تحديد أي مقاطع للتصدير")
    for c in clips:
        if c["end"] - c["start"] < 0.2:
            raise UserError(f"مدة المقطع \"{c['name']}\" قصيرة جدًا أو توقيته غير صحيح")
    tpl = storage.get_template(template_id) if template_id else None
    background = storage.template_file(template_id, "background") if tpl else None
    fps = (project.get("media") or {}).get("fps") or "30/1"
    venc = media.video_encoder_args()

    out_dir = os.path.join(config.paths().outputs, storage.safe_filename(folder or project["name"]))
    os.makedirs(out_dir, exist_ok=True)
    work = os.path.join(config.paths().work, job.id)
    os.makedirs(work, exist_ok=True)
    files = []
    try:
        for i, clip in enumerate(clips):
            job.check_cancel()
            label = f"المقطع {i + 1} من {len(clips)}: {clip['name']}"
            job.update(progress=i / len(clips), message=f"جارٍ تصدير {label}")
            filename = f"{i + 1:02d}_{storage.safe_filename(clip['name'])}.mp4"
            tmp_out = os.path.join(work, filename)
            if tpl:
                overlay = None
                if overlays.get(clip["id"]):
                    _, png = storage.decode_data_url(overlays[clip["id"]])
                    overlay = os.path.join(work, f"overlay_{i}.png")
                    with open(overlay, "wb") as f:
                        f.write(png)
                args = media.build_template_args(video, clip["start"], clip["end"], background,
                                                 overlay, tpl, tmp_out, venc, fps=fps)
            else:
                args = media.build_cut_args(video, clip["start"], clip["end"], tmp_out, cut_mode, venc)
            media.run_ffmpeg(args, duration=clip["end"] - clip["start"], cancel_event=job.cancel_event,
                             progress_cb=lambda p, i=i: job.update(progress=(i + p) / len(clips)))
            job.update(message=f"جارٍ حفظ {label} على الدرايف...")
            dest = _unique_path(out_dir, filename)
            shutil.copyfile(tmp_out, dest)
            os.remove(tmp_out)
            files.append(storage.to_drive_rel(dest))
    finally:
        shutil.rmtree(work, ignore_errors=True)

    record = {"at": storage.now_iso(), "folder": storage.to_drive_rel(out_dir), "files": files,
              "template_id": template_id}
    storage.update_project(pid, lambda p: p.setdefault("exports", []).append(record))
    return record
