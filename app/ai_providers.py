"""REST clients for Gemini Studio and OpenRouter — plain requests, no heavy SDKs."""
import logging
import time

import requests

logger = logging.getLogger(__name__)

GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"
OPENROUTER_BASE = "https://openrouter.ai/api/v1"

DEFAULT_GEMINI_MODEL = "gemini-2.0-flash"
DEFAULT_OPENROUTER_MODEL = "openai/gpt-4o-mini"

TIMEOUT = 120
MAX_ATTEMPTS = 4
BACKOFF_BASE_SECONDS = 1.5
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


class AIProviderError(Exception):
    pass


def post_with_retry(url: str, **kwargs) -> requests.Response:
    """POST with exponential backoff on network errors, 429, and 5xx responses."""
    last_error = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            resp = requests.post(url, timeout=TIMEOUT, **kwargs)
        except (requests.ConnectionError, requests.Timeout) as e:
            last_error = e
            logger.warning("Network error (attempt %d/%d): %s", attempt, MAX_ATTEMPTS, e)
        else:
            if resp.status_code not in RETRYABLE_STATUS_CODES:
                return resp
            last_error = AIProviderError(f"HTTP {resp.status_code}: {resp.text[:300]}")
            logger.warning(
                "Retryable HTTP %s (attempt %d/%d)", resp.status_code, attempt, MAX_ATTEMPTS
            )
        if attempt < MAX_ATTEMPTS:
            time.sleep(BACKOFF_BASE_SECONDS ** attempt)
    raise AIProviderError(f"فشل الاتصال بعد {MAX_ATTEMPTS} محاولات: {last_error}")


class BaseProvider:
    def generate(self, prompt: str) -> str:
        raise NotImplementedError

    def test_connection(self) -> tuple[bool, str]:
        try:
            reply = self.generate("Reply with the single word: ok")
            return True, reply.strip()[:200]
        except Exception as e:  # noqa: BLE001 - surfaced to the UI as-is
            return False, str(e)


class GeminiProvider(BaseProvider):
    def __init__(self, api_key: str, model: str = DEFAULT_GEMINI_MODEL):
        self.api_key = api_key
        self.model = model or DEFAULT_GEMINI_MODEL

    def generate(self, prompt: str) -> str:
        url = f"{GEMINI_BASE}/models/{self.model}:generateContent"
        resp = post_with_retry(
            url,
            params={"key": self.api_key},
            json={"contents": [{"parts": [{"text": prompt}]}]},
        )
        if resp.status_code != 200:
            raise AIProviderError(f"Gemini API error {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
        try:
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError) as e:
            raise AIProviderError(f"استجابة Gemini غير متوقعة: {data}") from e


class OpenRouterProvider(BaseProvider):
    def __init__(self, api_key: str, model: str = DEFAULT_OPENROUTER_MODEL):
        self.api_key = api_key
        self.model = model or DEFAULT_OPENROUTER_MODEL

    def generate(self, prompt: str) -> str:
        resp = post_with_retry(
            f"{OPENROUTER_BASE}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        if resp.status_code != 200:
            raise AIProviderError(f"OpenRouter API error {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as e:
            raise AIProviderError(f"استجابة OpenRouter غير متوقعة: {data}") from e


def get_provider(name: str, api_key: str, model: str) -> BaseProvider:
    if name == "gemini":
        return GeminiProvider(api_key, model)
    if name == "openrouter":
        return OpenRouterProvider(api_key, model)
    raise AIProviderError(f"مزود غير مدعوم: {name}")
