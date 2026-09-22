"""Build AI prompts from the transcript and parse the response into Topics."""
import json
import re

from .ai_providers import BaseProvider, AIProviderError
from .models import Segment, Topic
from .transcription import transcript_as_text

PROMPTS = {
    "social_clips": (
        "أنت محلل محتوى فيديو. لديك نص مفرغ من فيديو مع توقيتات (الوقت بالثواني).\n"
        "مهمتك: استخرج مقاطع ذات معنى مكتمل تصلح كمقاطع قصيرة لمنصات التواصل الاجتماعي "
        "(مدة كل مقطع بين 15 و90 ثانية تقريبًا، ويجب أن تبدأ وتنتهي عند حدود جمل كاملة).\n"
        "أعد النتيجة بصيغة JSON فقط (بدون أي شرح إضافي) كمصفوفة من العناصر بالشكل التالي:\n"
        '[{{"name": "عنوان الموضوع", "text": "النص الكامل للمقطع", '
        '"start": 12.5, "end": 45.2}}]\n'
        "استخدم قيم start/end بالثواني (أرقام عشرية) مطابقة لتوقيتات النص أدناه.\n\n"
        "النص المفرغ:\n{transcript}\n"
    ),
    "lecture_sections": (
        "أنت محلل محتوى تعليمي. لديك نص مفرغ من محاضرة طويلة مع توقيتات (الوقت بالثواني).\n"
        "مهمتك: قسّم المحاضرة إلى أقسام رئيسية بعناوين واضحة، كل قسم يغطي فكرة أو موضوعًا "
        "متكاملاً من بدايته إلى نهايته.\n"
        "أعد النتيجة بصيغة JSON فقط (بدون أي شرح إضافي) كمصفوفة من العناصر بالشكل التالي:\n"
        '[{{"name": "عنوان القسم", "text": "ملخص أو النص الخاص بالقسم", '
        '"start": 0.0, "end": 300.0}}]\n'
        "استخدم قيم start/end بالثواني (أرقام عشرية) مطابقة لتوقيتات النص أدناه.\n\n"
        "النص المفرغ:\n{transcript}\n"
    ),
}


class AnalysisError(Exception):
    pass


def build_prompt(mode: str, segments: list[Segment]) -> str:
    if mode not in PROMPTS:
        raise AnalysisError(f"نمط تحليل غير مدعوم: {mode}")
    transcript = transcript_as_text(segments)
    return PROMPTS[mode].format(transcript=transcript)


def _extract_json_array(text: str) -> list:
    fenced = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, re.DOTALL)
    candidate = fenced.group(1) if fenced else text
    match = re.search(r"\[.*\]", candidate, re.DOTALL)
    if not match:
        raise AnalysisError("لم يتم العثور على JSON صالح في رد الذكاء الاصطناعي")
    return json.loads(match.group(0))


def analyze(provider: BaseProvider, mode: str, segments: list[Segment],
            project_id: int) -> list[Topic]:
    prompt = build_prompt(mode, segments)
    try:
        raw = provider.generate(prompt)
    except AIProviderError:
        raise
    items = _extract_json_array(raw)

    topics = []
    for idx, item in enumerate(items):
        start = float(item.get("start", 0))
        end = float(item.get("end", start))
        topics.append(Topic(
            id=None, project_id=project_id, mode=mode,
            name=str(item.get("name", f"موضوع {idx + 1}")),
            text=str(item.get("text", "")),
            start=start, end=end, duration=max(end - start, 0),
            selected=True, order_index=idx,
        ))
    return topics
