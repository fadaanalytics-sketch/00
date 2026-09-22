import pytest

from app.analysis import analyze, AnalysisError
from app.ai_providers import BaseProvider
from app.models import Segment


class FakeProvider(BaseProvider):
    def __init__(self, reply: str):
        self.reply = reply

    def generate(self, prompt: str) -> str:
        return self.reply


RAW_ITEMS = '[{"name": "مقدمة", "text": "كلام", "start": 0.0, "end": 12.5}]'


def test_analyze_builds_topics_from_provider_reply():
    provider = FakeProvider(f"```json\n{RAW_ITEMS}\n```")
    segments = [Segment(start=0.0, end=12.5, text="كلام")]
    topics = analyze(provider, "social_clips", segments, project_id=7)
    assert len(topics) == 1
    t = topics[0]
    assert t.project_id == 7
    assert t.mode == "social_clips"
    assert t.name == "مقدمة"
    assert t.start == 0.0
    assert t.end == 12.5
    assert t.duration == pytest.approx(12.5)
    assert t.selected is True


def test_analyze_unsupported_mode_raises():
    provider = FakeProvider(RAW_ITEMS)
    with pytest.raises(AnalysisError):
        analyze(provider, "not_a_real_mode", [], project_id=1)


def test_analyze_no_json_in_reply_raises_analysis_error():
    provider = FakeProvider("لا يوجد شيء هنا")
    with pytest.raises(AnalysisError):
        analyze(provider, "social_clips", [], project_id=1)
