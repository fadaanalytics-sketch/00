import pytest

from app.json_utils import JsonExtractionError, extract_json_array

RAW_ITEMS = '[{"name": "مقدمة", "text": "كلام", "start": 0.0, "end": 12.5}]'


def test_extract_json_array_plain():
    assert extract_json_array(RAW_ITEMS) == [
        {"name": "مقدمة", "text": "كلام", "start": 0.0, "end": 12.5}
    ]


def test_extract_json_array_fenced_with_surrounding_text():
    text = f"طبعًا، إليك النتيجة:\n```json\n{RAW_ITEMS}\n```\nشكرًا"
    assert extract_json_array(text) == [
        {"name": "مقدمة", "text": "كلام", "start": 0.0, "end": 12.5}
    ]


def test_extract_json_array_no_json_raises():
    with pytest.raises(JsonExtractionError):
        extract_json_array("لا يوجد شيء هنا")
