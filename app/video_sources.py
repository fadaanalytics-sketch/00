"""Resolve a video source (local file / YouTube / Google Drive) into a local file path."""
import os
import re
import shutil


class VideoSourceError(Exception):
    pass


def import_local(path: str, dest_dir: str) -> str:
    if not os.path.isfile(path):
        raise VideoSourceError(f"الملف غير موجود: {path}")
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, os.path.basename(path))
    if os.path.abspath(dest) != os.path.abspath(path):
        shutil.copy2(path, dest)
    return dest


def download_youtube(url: str, dest_dir: str, progress_hook=None) -> str:
    try:
        import yt_dlp
    except ImportError as e:
        raise VideoSourceError("مكتبة yt-dlp غير مثبتة") from e

    os.makedirs(dest_dir, exist_ok=True)
    out_tmpl = os.path.join(dest_dir, "%(title).80s.%(ext)s")
    ydl_opts = {
        "outtmpl": out_tmpl,
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "merge_output_format": "mp4",
        "quiet": True,
        "noplaylist": True,
    }
    if progress_hook:
        ydl_opts["progress_hooks"] = [progress_hook]

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        return ydl.prepare_filename(info).rsplit(".", 1)[0] + ".mp4" \
            if not ydl.prepare_filename(info).endswith(".mp4") else ydl.prepare_filename(info)


_GDRIVE_ID_RE = re.compile(r"(?:/d/|id=)([a-zA-Z0-9_-]{20,})")


def _extract_gdrive_id(url: str) -> str:
    m = _GDRIVE_ID_RE.search(url)
    if not m:
        raise VideoSourceError("تعذر استخراج معرف الملف من رابط Google Drive")
    return m.group(1)


def download_gdrive(url: str, dest_dir: str) -> str:
    try:
        import gdown
    except ImportError as e:
        raise VideoSourceError("مكتبة gdown غير مثبتة") from e

    os.makedirs(dest_dir, exist_ok=True)
    file_id = _extract_gdrive_id(url)
    dest = os.path.join(dest_dir, f"{file_id}.mp4")
    result = gdown.download(id=file_id, output=dest, quiet=False, fuzzy=True)
    if not result:
        raise VideoSourceError("فشل تحميل الملف من Google Drive")
    return result


def resolve_video(source_type: str, source: str, dest_dir: str, progress_hook=None) -> str:
    if source_type == "local":
        return import_local(source, dest_dir)
    if source_type == "youtube":
        return download_youtube(source, dest_dir, progress_hook)
    if source_type == "gdrive":
        return download_gdrive(source, dest_dir)
    raise VideoSourceError(f"نوع مصدر غير مدعوم: {source_type}")
