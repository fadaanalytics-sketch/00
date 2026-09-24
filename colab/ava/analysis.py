"""Turn a transcript into clip suggestions via an LLM, then tidy the boundaries."""
import secrets

from .errors import UserError
from .json_utils import JsonExtractionError, extract_json_array

PROMPTS = {
    "social_clips": (
        "أنت محرر فيديو محترف. لديك نص مفرغ من فيديو، وكل سطر يبدأ بتوقيته بالثواني [البداية - النهاية].\n"
        "المطلوب: استخرج أفضل المقاطع التي تصلح كمقاطع قصيرة لمنصات التواصل الاجتماعي.\n"
        "الشروط:\n"
        "- كل مقطع له معنى مكتمل ومفهوم وحده بدون سياق خارجي.\n"
        "- مدة كل مقطع بين 15 و90 ثانية تقريبًا.\n"
        "- يبدأ وينتهي عند حدود جمل كاملة.\n"
        "- عنوان جذاب وقصير (من 3 إلى 8 كلمات) يصلح للظهور على الفيديو.\n"
        "أعد النتيجة بصيغة JSON فقط كمصفوفة بالشكل التالي:\n"
        '[{{"name": "عنوان المقطع", "text": "ملخص أو نص المقطع", "start": 12.5, "end": 45.2}}]\n'
        "قيم start/end بالثواني مطابقة لتوقيتات النص.\n\n"
        "النص المفرغ:\n{transcript}\n"
    ),
    "lecture_sections": (
        "أنت محلل محتوى تعليمي. لديك نص مفرغ من محاضرة، وكل سطر يبدأ بتوقيته بالثواني [البداية - النهاية].\n"
        "المطلوب: قسّم المحاضرة إلى أقسام رئيسية متتالية، كل قسم يغطي موضوعًا متكاملًا من بدايته لنهايته، "
        "بعنوان واضح ومختصر.\n"
        "أعد النتيجة بصيغة JSON فقط كمصفوفة بالشكل التالي:\n"
        '[{{"name": "عنوان القسم", "text": "ملخص القسم", "start": 0.0, "end": 300.0}}]\n'
        "قيم start/end بالثواني مطابقة لتوقيتات النص.\n\n"
        "النص المفرغ:\n{transcript}\n"
    ),
}


def transcript_for_prompt(segments: list[dict]) -> str:
    # Seconds, not HH:MM:SS: the model is asked to answer in seconds, and matching
    # the input format avoids conversion mistakes.
    return "\n".join(f"[{s['start']:.1f} - {s['end']:.1f}] {s['text']}" for s in segments)


def build_prompt(mode: str, segments: list[dict]) -> str:
    if mode not in PROMPTS:
        raise UserError(f"نمط تحليل غير مدعوم: {mode}")
    if not segments:
        raise UserError("لا يوجد نص مفرغ - قم بالتفريغ الصوتي أولاً")
    return PROMPTS[mode].format(transcript=transcript_for_prompt(segments))


def new_topic_id() -> str:
    return f"t_{secrets.token_hex(4)}"


def parse_topics(raw: str, duration: float) -> list[dict]:
    try:
        items = extract_json_array(raw)
    except JsonExtractionError as e:
        raise UserError(str(e)) from e
    limit = duration if duration and duration > 0 else float("inf")
    topics = []
    for i, it in enumerate(items):
        if not isinstance(it, dict):
            continue
        try:
            start, end = float(it.get("start", 0)), float(it.get("end", 0))
        except (TypeError, ValueError):
            continue
        start, end = max(0.0, min(start, limit)), max(0.0, min(end, limit))
        if end - start < 0.5:
            continue
        topics.append({"id": new_topic_id(), "name": str(it.get("name") or f"مقطع {i + 1}").strip(),
                       "text": str(it.get("text") or "").strip(),
                       "start": round(start, 2), "end": round(end, 2), "selected": True})
    topics.sort(key=lambda t: t["start"])
    return topics


def _all_words(segments: list[dict]) -> list:
    words = [w for s in segments for w in (s.get("words") or [])]
    words.sort(key=lambda w: w[0])
    return words


def snap_range(start: float, end: float, words: list, duration: float,
               pad_start: float = 0.1, pad_end: float = 0.15) -> tuple[float, float]:
    """Move boundaries onto word edges: start at the first word still being spoken
    at/after `start` (so a cut never lands mid-word, and leading silence is
    skipped), end at the last word that started before `end`."""
    first = next((w for w in words if w[1] > start), None)
    last = next((w for w in reversed(words) if w[0] < end), None)
    if first is None or last is None or last[1] <= first[0]:
        return start, end
    s = max(0.0, first[0] - pad_start)
    e = last[1] + pad_end
    if duration:
        e = min(e, duration)
    return round(s, 2), round(e, 2)


def snap_topics_to_words(topics: list[dict], segments: list[dict], duration: float) -> list[dict]:
    words = _all_words(segments)
    if not words:
        return topics
    for t in topics:
        t["start"], t["end"] = snap_range(t["start"], t["end"], words, duration)
    return topics


def clean_topics(raw_topics: list[dict], duration: float) -> list[dict]:
    """Validate topics edited in the UI."""
    limit = duration if duration and duration > 0 else float("inf")
    out = []
    for t in raw_topics:
        try:
            start, end = float(t.get("start", 0)), float(t.get("end", 0))
        except (TypeError, ValueError):
            raise UserError("توقيت غير صالح في أحد المقاطع")
        start, end = max(0.0, min(start, limit)), max(0.0, min(end, limit))
        out.append({"id": str(t.get("id") or new_topic_id()), "name": str(t.get("name") or "").strip(),
                    "text": str(t.get("text") or "").strip(), "start": round(start, 2),
                    "end": round(end, 2), "selected": bool(t.get("selected", True))})
    return out
