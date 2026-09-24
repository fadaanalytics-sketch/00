import pytest

from ava import analysis
from ava.errors import UserError

WORDS = [[1.0, 1.4, " أهلا"], [1.5, 2.0, " بيكم"], [4.0, 4.5, " النهارده"], [4.6, 5.2, " هنتكلم"]]
SEGMENTS = [{"start": 1.0, "end": 2.0, "text": "أهلا بيكم", "words": WORDS[:2]},
            {"start": 4.0, "end": 5.2, "text": "النهارده هنتكلم", "words": WORDS[2:]}]


def test_prompt_uses_seconds_to_match_the_requested_output():
    prompt = analysis.build_prompt("social_clips", SEGMENTS)
    assert "[1.0 - 2.0] أهلا بيكم" in prompt
    with pytest.raises(UserError):
        analysis.build_prompt("social_clips", [])
    with pytest.raises(UserError):
        analysis.build_prompt("nope", SEGMENTS)


def test_parse_topics_clamps_sorts_and_drops_junk():
    raw = """```json
    [{"name": "ب", "start": 50, "end": 999},
     {"name": "أ", "start": 10, "end": 20},
     {"name": "صغير", "start": 5, "end": 5.2},
     {"name": "مش رقم", "start": "x", "end": 3},
     "junk"]
    ```"""
    topics = analysis.parse_topics(raw, duration=60)
    assert [t["name"] for t in topics] == ["أ", "ب"]
    assert topics[1]["end"] == 60
    assert all(t["selected"] and t["id"].startswith("t_") for t in topics)
    with pytest.raises(UserError):
        analysis.parse_topics("no json here", 60)


@pytest.mark.parametrize("start,end,expected", [
    (1.2, 4.8, (0.9, 5.35)),   # start mid-word -> back to word start; end mid-word -> word end
    (2.5, 5.0, (3.9, 5.35)),   # start in silence -> first word after it
    (0.0, 2.2, (0.9, 2.15)),
])
def test_snap_range(start, end, expected):
    assert analysis.snap_range(start, end, WORDS, duration=60) == pytest.approx(expected)


def test_snap_range_keeps_bounds_without_words_or_when_degenerate():
    assert analysis.snap_range(1.0, 2.0, [], 60) == (1.0, 2.0)
    assert analysis.snap_range(2.1, 3.9, WORDS, 60) == (2.1, 3.9)  # no word inside the range


def test_snap_topics_skips_transcripts_without_words():
    topics = [{"start": 1.2, "end": 4.8}]
    assert analysis.snap_topics_to_words(topics, [{"start": 0, "end": 5, "text": "x"}], 60) == [{"start": 1.2, "end": 4.8}]


def test_clean_topics_validates_ui_edits():
    cleaned = analysis.clean_topics([{"name": " x ", "start": "1.5", "end": 999, "selected": 0}], duration=30)
    assert cleaned[0]["name"] == "x" and cleaned[0]["end"] == 30 and cleaned[0]["selected"] is False
    assert cleaned[0]["id"].startswith("t_")
    with pytest.raises(UserError):
        analysis.clean_topics([{"start": "abc", "end": 3}], 30)
