"""Pull a JSON array out of an LLM's free-form text reply."""
import json
import re


class JsonExtractionError(Exception):
    pass


def extract_json_array(text: str) -> list:
    fenced = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, re.DOTALL)
    candidate = fenced.group(1) if fenced else text
    match = re.search(r"\[.*\]", candidate, re.DOTALL)
    if not match:
        raise JsonExtractionError("لم يتم العثور على JSON صالح في رد الذكاء الاصطناعي")
    return json.loads(match.group(0))
