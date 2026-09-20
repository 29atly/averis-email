"""Small REST adapters, without provider SDK dependencies."""
import json
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from .config import Settings


class ProviderError(Exception):
    """Provider/network failure. Never includes credentials or response bodies."""


class InvalidResponse(Exception):
    """Blocked, truncated, or malformed provider response."""


class Provider(Protocol):
    def complete(self, system: str, text: str, schema: dict) -> str: ...


def post_json(url: str, headers: dict, payload: dict, timeout: float) -> dict:
    request = Request(url, data=json.dumps(payload).encode("utf-8"),
                      headers={"Content-Type": "application/json", **headers}, method="POST")
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.load(response)
    except HTTPError as exc:
        raise ProviderError(f"Provider returned HTTP {exc.code}") from None
    except (URLError, TimeoutError, OSError):
        raise ProviderError("Provider connection failed or timed out") from None
    except (ValueError, UnicodeError):
        raise InvalidResponse("Provider did not return valid JSON") from None


class ChatProvider:
    """Shared chat-completions transport for NVIDIA and Hugging Face."""
    def __init__(self, settings: Settings):
        self.settings = settings

    def output_constraint(self, schema: dict) -> dict:
        raise NotImplementedError

    def complete(self, system: str, text: str, schema: dict) -> str:
        s = self.settings
        data = post_json(s.base_url.rstrip("/") + "/chat/completions",
                         {"Authorization": f"Bearer {s.api_key.get_secret_value()}"},
                         {"model": s.model, "messages": [
                             {"role": "system", "content": system},
                             {"role": "user", "content": text}],
                          "temperature": 0, "max_tokens": s.max_output_tokens,
                          "stream": False, **self.output_constraint(schema)}, s.timeout)
        try:
            choice = data["choices"][0]
            if choice["finish_reason"] != "stop" or choice["message"].get("refusal"):
                raise InvalidResponse("Provider refused or did not finish the response")
            content = choice["message"]["content"]
            if not isinstance(content, str) or not content.strip():
                raise InvalidResponse("Provider returned no text")
            return content
        except (KeyError, IndexError, TypeError, AttributeError):
            raise InvalidResponse("Unexpected provider response structure") from None


class NvidiaProvider(ChatProvider):
    def output_constraint(self, schema: dict) -> dict:
        return {"guided_json": schema}


class HuggingFaceProvider(ChatProvider):
    def output_constraint(self, schema: dict) -> dict:
        return {"response_format": {"type": "json_schema", "json_schema": {
            "name": "email_classification", "strict": True, "schema": schema}}}


class GeminiProvider:
    def __init__(self, settings: Settings):
        self.settings = settings

    def complete(self, system: str, text: str, schema: dict) -> str:
        s = self.settings
        model = quote(s.model.removeprefix("models/"), safe="")
        data = post_json(f"{s.base_url.rstrip('/')}/models/{model}:generateContent",
                         {"x-goog-api-key": s.api_key.get_secret_value()},
                         {"systemInstruction": {"parts": [{"text": system}]},
                          "contents": [{"role": "user", "parts": [{"text": text}]}],
                          "generationConfig": {"temperature": 0,
                              "maxOutputTokens": s.max_output_tokens,
                              "responseMimeType": "application/json",
                              "responseJsonSchema": schema}}, s.timeout)
        try:
            candidate = data["candidates"][0]
            if candidate["finishReason"] != "STOP":
                raise InvalidResponse("Provider blocked or did not finish the response")
            content = "".join(part["text"] for part in candidate["content"]["parts"]
                              if not part.get("thought", False))
            if not content.strip():
                raise InvalidResponse("Provider returned no text")
            return content
        except (KeyError, IndexError, TypeError, AttributeError):
            raise InvalidResponse("Unexpected provider response structure") from None


def make_provider(settings: Settings) -> Provider:
    return {"nvidia": NvidiaProvider, "gemini": GeminiProvider,
            "huggingface": HuggingFaceProvider}[settings.provider](settings)
