"""Cloud transcription via the Gemini API's native audio understanding.

Alternative to local faster-whisper transcription for machines too weak/slow
to run it: extracts the audio track with ffmpeg, uploads it to Gemini's Files
API, waits for it to finish processing, then asks the model to transcribe it
with timestamps. Uses the same Gemini API key already configured for AI
analysis - no extra account or local model download needed, but the audio
does leave the machine and is subject to Gemini's API quotas/limits.
"""
import os
import shutil
import subprocess
import tempfile
import threading
import time
from typing import Callable, Optional

import requests

from .ai_providers import AIProviderError, TIMEOUT, post_with_retry
from .config import CANCELLED_MESSAGE
from .json_utils import JsonExtractionError, extract_json_array
from .models import Segment
from .transcription import CancelledError, LANGUAGES, TranscriptionError

GEMINI_FILES_BASE = "https://generativelanguage.googleapis.com/v1beta"
GEMINI_UPLOAD_URL = "https://generativelanguage.googleapis.com/upload/v1beta/files"
DEFAULT_MODEL = "gemini-2.0-flash"
AUDIO_MIME_TYPE = "audio/aac"

POLL_INTERVAL_SECONDS = 2
POLL_TIMEOUT_SECONDS = 120

PROMPT_TEMPLATE = (
    "استمع إلى الملف الصوتي المرفق بعناية، ثم فرّغه (Speech-to-Text) بالكامل من "
    "البداية للنهاية بدون تلخيص أو ترجمة.{language_hint}\n"
    "قسّم النص إلى مقاطع قصيرة (جملة أو جملتين لكل مقطع) وأعد النتيجة بصيغة JSON "
    "فقط بدون أي شرح إضافي، كمصفوفة من العناصر بالشكل التالي:\n"
    '[{{"start": 0.0, "end": 4.2, "text": "..."}}]\n'
    "قيم start/end بالثواني (أرقام عشرية) وتمثل توقيت بداية ونهاية كل مقطع من "
    "بداية الملف الصوتي، ويجب أن تغطي المقاطع كامل مدة الملف دون فجوات كبيرة."
)


def _ffmpeg_bin() -> str:
    path = shutil.which("ffmpeg")
    if not path:
        raise TranscriptionError(
            "FFmpeg غير مثبت أو غير موجود في PATH. لو ثبّته للتو، تأكد من إغلاق "
            "التطبيق تمامًا وإعادة فتحه (أو إعادة تشغيل الجهاز) - البرنامج يقرأ "
            "متغير PATH وقت فتحه فقط، فتعديله لا يؤثر على نسخة مفتوحة بالفعل."
        )
    return path


def _extract_audio(video_path: str, out_path: str):
    ffmpeg = _ffmpeg_bin()
    cmd = [
        ffmpeg, "-y", "-i", video_path, "-vn",
        "-ac", "1", "-ar", "16000", "-c:a", "aac", "-b:a", "64k", out_path,
    ]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if proc.returncode != 0:
        raise TranscriptionError(f"فشل استخراج الصوت عبر FFmpeg:\n{proc.stdout[-2000:]}")


def _upload_file(audio_path: str, api_key: str) -> tuple[str, str]:
    """Uploads via Gemini's resumable Files API. Returns (file_name, file_uri)."""
    size = os.path.getsize(audio_path)

    start_resp = post_with_retry(
        GEMINI_UPLOAD_URL,
        params={"key": api_key},
        headers={
            "X-Goog-Upload-Protocol": "resumable",
            "X-Goog-Upload-Command": "start",
            "X-Goog-Upload-Header-Content-Length": str(size),
            "X-Goog-Upload-Header-Content-Type": AUDIO_MIME_TYPE,
            "Content-Type": "application/json",
        },
        json={"file": {"display_name": os.path.basename(audio_path)}},
    )
    if start_resp.status_code not in (200, 201):
        raise AIProviderError(
            f"فشل بدء رفع الملف إلى Gemini: {start_resp.status_code} {start_resp.text[:300]}"
        )
    upload_url = start_resp.headers.get("X-Goog-Upload-URL") or start_resp.headers.get(
        "x-goog-upload-url"
    )
    if not upload_url:
        raise AIProviderError("لم يتم استلام رابط الرفع من Gemini")

    with open(audio_path, "rb") as f:
        audio_bytes = f.read()
    upload_resp = requests.post(
        upload_url,
        headers={
            "Content-Length": str(size),
            "X-Goog-Upload-Offset": "0",
            "X-Goog-Upload-Command": "upload, finalize",
        },
        data=audio_bytes,
        timeout=TIMEOUT,
    )
    if upload_resp.status_code not in (200, 201):
        raise AIProviderError(
            f"فشل رفع الملف إلى Gemini: {upload_resp.status_code} {upload_resp.text[:300]}"
        )
    file_info = upload_resp.json().get("file", {})
    file_uri = file_info.get("uri")
    file_name = file_info.get("name")
    if not file_uri or not file_name:
        raise AIProviderError(f"استجابة رفع غير متوقعة من Gemini: {upload_resp.text[:300]}")
    return file_name, file_uri


def _wait_until_active(file_name: str, api_key: str, cancel_event: Optional[threading.Event] = None):
    deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if cancel_event is not None and cancel_event.is_set():
            raise CancelledError(CANCELLED_MESSAGE)
        resp = requests.get(
            f"{GEMINI_FILES_BASE}/{file_name}", params={"key": api_key}, timeout=TIMEOUT
        )
        if resp.status_code != 200:
            raise AIProviderError(f"فشل التحقق من حالة الملف على Gemini: {resp.status_code}")
        state = resp.json().get("state")
        if state == "ACTIVE":
            return
        if state == "FAILED":
            raise AIProviderError("فشلت معالجة الملف على خوادم Gemini")
        time.sleep(POLL_INTERVAL_SECONDS)
    raise TranscriptionError("انتهت المهلة أثناء انتظار معالجة الملف على خوادم Gemini")


def _request_transcript(file_uri: str, api_key: str, model: str, language: Optional[str]) -> str:
    language_hint = ""
    if language:
        language_name = LANGUAGES.get(language, language)
        language_hint = f" اللغة المستخدمة في الملف هي: {language_name}."
    prompt = PROMPT_TEMPLATE.format(language_hint=language_hint)

    resp = post_with_retry(
        f"{GEMINI_FILES_BASE}/models/{model}:generateContent",
        params={"key": api_key},
        json={
            "contents": [{
                "parts": [
                    {"fileData": {"mimeType": AUDIO_MIME_TYPE, "fileUri": file_uri}},
                    {"text": prompt},
                ]
            }]
        },
    )
    if resp.status_code != 200:
        raise AIProviderError(f"خطأ من Gemini API {resp.status_code}: {resp.text[:300]}")
    data = resp.json()
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as e:
        raise AIProviderError(f"استجابة Gemini غير متوقعة: {data}") from e


def transcribe_via_gemini(
    video_path: str,
    api_key: str,
    model: str = DEFAULT_MODEL,
    language: Optional[str] = None,
    progress_cb: Optional[Callable[[float], None]] = None,
    status_cb: Optional[Callable[[str], None]] = None,
    cancel_event: Optional[threading.Event] = None,
) -> list[Segment]:
    if not api_key:
        raise TranscriptionError("مفتاح Gemini API غير موجود - أدخله من الإعدادات أولاً")

    def check_cancel():
        if cancel_event is not None and cancel_event.is_set():
            raise CancelledError(CANCELLED_MESSAGE)

    tmp_dir = tempfile.mkdtemp(prefix="av_gemini_")
    audio_path = os.path.join(tmp_dir, "audio.aac")
    try:
        if status_cb:
            status_cb("جارٍ استخراج الصوت من الفيديو...")
        _extract_audio(video_path, audio_path)
        if progress_cb:
            progress_cb(0.15)
        check_cancel()

        if status_cb:
            status_cb("جارٍ رفع الملف الصوتي إلى Gemini...")
        file_name, file_uri = _upload_file(audio_path, api_key)
        if progress_cb:
            progress_cb(0.45)
        check_cancel()

        if status_cb:
            status_cb("جارٍ معالجة الملف على خوادم Gemini...")
        _wait_until_active(file_name, api_key, cancel_event)
        if progress_cb:
            progress_cb(0.6)
        check_cancel()

        if status_cb:
            status_cb("جارٍ التفريغ الصوتي بواسطة Gemini...")
        raw_text = _request_transcript(file_uri, api_key, model, language)

        try:
            items = extract_json_array(raw_text)
        except JsonExtractionError as e:
            raise TranscriptionError(str(e)) from e

        segments = [
            Segment(
                start=float(item.get("start", 0)),
                end=float(item.get("end", 0)),
                text=str(item.get("text", "")).strip(),
            )
            for item in items
        ]
        if progress_cb:
            progress_cb(1.0)
        return segments
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
