"""Gemini / OpenRouter REST clients (plain requests), plus Gemini audio transcription."""
import glob
import logging
import os
import shutil
import tempfile
import time

import requests

from . import config, media
from .errors import Cancelled, UserError
from .json_utils import JsonExtractionError, extract_json_array

logger = logging.getLogger(__name__)

GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"
GEMINI_UPLOAD_URL = "https://generativelanguage.googleapis.com/upload/v1beta/files"
OPENROUTER_BASE = "https://openrouter.ai/api/v1"

TIMEOUT = 300
MAX_ATTEMPTS = 4
RETRYABLE_STATUS = {429, 500, 502, 503, 504}
# Long audio is transcribed in chunks: one giant request risks hitting the output
# token limit (the JSON transcript of an hour of speech is huge) and gives no progress.
TRANSCRIBE_CHUNK_SECONDS = 600
AUDIO_MIME = "audio/aac"

TRANSCRIBE_PROMPT = (
    "استمع إلى الملف الصوتي المرفق بعناية، ثم فرّغه (Speech-to-Text) بالكامل من البداية "
    "للنهاية بدون تلخيص أو ترجمة.{language_hint}\n"
    "قسّم النص إلى مقاطع قصيرة (جملة أو جملتين لكل مقطع) وأعد النتيجة بصيغة JSON فقط "
    "كمصفوفة من العناصر بالشكل التالي:\n"
    '[{{"start": 0.0, "end": 4.2, "text": "..."}}]\n'
    "قيم start/end بالثواني (أرقام عشرية) من بداية هذا الملف الصوتي، ويجب أن تغطي "
    "المقاطع كامل مدة الملف دون فجوات كبيرة."
)


class LLMError(Exception):
    pass


def _request(method: str, url: str, **kwargs) -> requests.Response:
    """HTTP with exponential backoff on network errors, 429 and 5xx."""
    last_error = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            resp = requests.request(method, url, timeout=TIMEOUT, **kwargs)
        except (requests.ConnectionError, requests.Timeout) as e:
            last_error = e
        else:
            if resp.status_code not in RETRYABLE_STATUS:
                return resp
            last_error = f"HTTP {resp.status_code}: {resp.text[:300]}"
        logger.warning("request failed (attempt %d/%d): %s", attempt, MAX_ATTEMPTS, last_error)
        if attempt < MAX_ATTEMPTS:
            time.sleep(1.5 ** attempt)
    raise LLMError(f"فشل الاتصال بعد {MAX_ATTEMPTS} محاولات: {last_error}")


def _gemini_text(data: dict) -> str:
    try:
        parts = data["candidates"][0]["content"]["parts"]
        return "".join(p.get("text", "") for p in parts)
    except (KeyError, IndexError) as e:
        reason = (data.get("promptFeedback") or {}).get("blockReason") or str(data)[:300]
        raise LLMError(f"استجابة غير متوقعة من Gemini: {reason}") from e


def gemini_generate(model: str, parts: list[dict], json_output: bool = True) -> str:
    key = config.gemini_key()
    if not key:
        raise UserError("مفتاح GEMINI_API_KEY غير موجود في Colab Secrets")
    body = {"contents": [{"parts": parts}]}
    if json_output:
        body["generationConfig"] = {"responseMimeType": "application/json"}
    resp = _request("POST", f"{GEMINI_BASE}/models/{model}:generateContent",
                    params={"key": key}, json=body)
    if resp.status_code != 200:
        raise LLMError(f"خطأ من Gemini ({resp.status_code}): {resp.text[:400]}")
    return _gemini_text(resp.json())


def openrouter_generate(model: str, prompt: str) -> str:
    key = config.openrouter_key()
    if not key:
        raise UserError("مفتاح OPENROUTER_API_KEY غير موجود في Colab Secrets")
    resp = _request("POST", f"{OPENROUTER_BASE}/chat/completions",
                    headers={"Authorization": f"Bearer {key}"},
                    json={"model": model, "messages": [{"role": "user", "content": prompt}]})
    if resp.status_code != 200:
        raise LLMError(f"خطأ من OpenRouter ({resp.status_code}): {resp.text[:400]}")
    try:
        return resp.json()["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as e:
        raise LLMError(f"استجابة غير متوقعة من OpenRouter: {resp.text[:300]}") from e


def generate_text(provider: str, model: str, prompt: str) -> str:
    if provider == "openrouter":
        return openrouter_generate(model, prompt)
    return gemini_generate(model, [{"text": prompt}])


# ---------- Gemini audio transcription ----------

def _upload_file(path: str) -> tuple[str, str]:
    key = config.gemini_key()
    size = os.path.getsize(path)
    start = _request("POST", GEMINI_UPLOAD_URL, params={"key": key}, headers={
        "X-Goog-Upload-Protocol": "resumable",
        "X-Goog-Upload-Command": "start",
        "X-Goog-Upload-Header-Content-Length": str(size),
        "X-Goog-Upload-Header-Content-Type": AUDIO_MIME,
        "Content-Type": "application/json",
    }, json={"file": {"display_name": os.path.basename(path)}})
    upload_url = start.headers.get("X-Goog-Upload-URL") or start.headers.get("x-goog-upload-url")
    if start.status_code not in (200, 201) or not upload_url:
        raise LLMError(f"فشل بدء رفع الصوت إلى Gemini ({start.status_code}): {start.text[:300]}")
    with open(path, "rb") as f:
        data = f.read()
    resp = _request("POST", upload_url, data=data, headers={
        "Content-Length": str(size), "X-Goog-Upload-Offset": "0",
        "X-Goog-Upload-Command": "upload, finalize",
    })
    info = resp.json().get("file", {}) if resp.status_code in (200, 201) else {}
    if not info.get("name") or not info.get("uri"):
        raise LLMError(f"فشل رفع الصوت إلى Gemini ({resp.status_code}): {resp.text[:300]}")
    return info["name"], info["uri"]


def _wait_active(name: str, cancel_event, timeout: float = 180):
    key = config.gemini_key()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if cancel_event is not None and cancel_event.is_set():
            raise Cancelled()
        resp = _request("GET", f"{GEMINI_BASE}/{name}", params={"key": key})
        state = resp.json().get("state") if resp.status_code == 200 else None
        if state == "ACTIVE":
            return
        if state == "FAILED":
            raise LLMError("فشلت معالجة الملف الصوتي على خوادم Gemini")
        time.sleep(2)
    raise LLMError("انتهت المهلة أثناء انتظار معالجة الملف على Gemini")


def _delete_file(name: str):
    try:
        requests.delete(f"{GEMINI_BASE}/{name}", params={"key": config.gemini_key()}, timeout=30)
    except requests.RequestException:
        pass  # files expire on their own after 48h


def gemini_transcribe(video_path: str, model: str, language: str | None, languages: dict,
                      progress_cb, status_cb, cancel_event) -> dict:
    if not config.gemini_key():
        raise UserError("التفريغ عبر Gemini يحتاج مفتاح GEMINI_API_KEY في Colab Secrets")
    work = tempfile.mkdtemp(prefix="ava_gemini_", dir=config.paths().work)
    try:
        status_cb("جارٍ استخراج الصوت من الفيديو...")
        media.run_ffmpeg(media.build_audio_chunks_args(
            video_path, os.path.join(work, "chunk_%03d.aac"), TRANSCRIBE_CHUNK_SECONDS),
            cancel_event=cancel_event)
        chunks = sorted(glob.glob(os.path.join(work, "chunk_*.aac")))
        if not chunks:
            raise UserError("لم يتم العثور على صوت في الفيديو")
        hint = ""
        if language:
            hint = f" اللغة المستخدمة في الملف هي: {languages.get(language, language)}."
        prompt = TRANSCRIBE_PROMPT.format(language_hint=hint)
        segments = []
        for i, chunk in enumerate(chunks):
            if cancel_event is not None and cancel_event.is_set():
                raise Cancelled()
            status_cb(f"جارٍ التفريغ عبر Gemini (جزء {i + 1} من {len(chunks)})...")
            # The segment muxer starts chunk i at the first packet at/after i*T, so
            # this offset is exact to within one audio packet and never drifts
            # (unlike summing ffprobe's bitrate-estimated ADTS durations).
            offset = i * TRANSCRIBE_CHUNK_SECONDS
            name, uri = _upload_file(chunk)
            try:
                _wait_active(name, cancel_event)
                raw = gemini_generate(model, [{"fileData": {"mimeType": AUDIO_MIME, "fileUri": uri}},
                                              {"text": prompt}])
            finally:
                _delete_file(name)
            try:
                items = extract_json_array(raw)
            except JsonExtractionError as e:
                raise LLMError(f"رد Gemini لا يحتوي على نص مفرغ صالح: {raw[:200]}") from e
            for it in items:
                try:
                    s, e_ = float(it.get("start", 0)), float(it.get("end", 0))
                except (TypeError, ValueError):
                    continue
                text = str(it.get("text", "")).strip()
                if text:
                    segments.append({"start": round(offset + s, 2),
                                     "end": round(offset + max(e_, s), 2), "text": text})
            progress_cb((i + 1) / len(chunks))
        return {"engine": "gemini", "model": model, "language": language or "", "segments": segments}
    finally:
        shutil.rmtree(work, ignore_errors=True)
