"""Chat model providers for the AI planner.

Ollama runs on the laptop and is the default. Groq and Gemini are optional free-tier cloud
providers that read their key from an environment variable, so no key is ever written to
``config.json``. Every provider is asked for JSON output at temperature 0.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal, Protocol

import httpx

from lapremote.config import AiConfig

ChatRole = Literal["user", "assistant"]

DEFAULT_OLLAMA_MODEL = "qwen2.5:7b"
SMALL_OLLAMA_MODEL = "qwen2.5:3b"
GROQ_DEFAULT_MODEL = "llama-3.3-70b-versatile"
GEMINI_DEFAULT_MODEL = "gemini-2.0-flash"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

# A cold start loads the model into memory first, which can take a while on a laptop CPU.
REQUEST_TIMEOUT = httpx.Timeout(90.0, connect=3.0)
CHECK_TIMEOUT = httpx.Timeout(3.0)


@dataclass(frozen=True)
class ChatMessage:
    role: ChatRole
    content: str


class ProviderError(Exception):
    """A provider call failed. ``message`` is short and safe to show on the phone."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class ChatProvider(Protocol):
    name: str
    model: str

    async def complete(self, system: str, messages: list[ChatMessage]) -> str:
        """Return the model's raw text answer."""

    async def check(self) -> str | None:
        """None when the provider is ready, otherwise a short reason it isn't."""


def recommended_ollama_model(total_ram_bytes: int) -> str:
    """qwen2.5:7b on 16 GB or more, qwen2.5:3b below that.

    Memory is rounded to the nearest whole GB, because a "16 GB" laptop reports a little
    less than 16 GiB once the GPU and firmware have reserved their share.
    """
    gigabytes = round(total_ram_bytes / 2**30)
    return DEFAULT_OLLAMA_MODEL if gigabytes >= 16 else SMALL_OLLAMA_MODEL


def _json(response: httpx.Response) -> Any:  # noqa: ANN401 - provider JSON is untyped
    try:
        return response.json()
    except ValueError as exc:
        raise ProviderError("The AI model sent back something unexpected.") from exc


class OllamaProvider:
    name = "ollama"

    def __init__(self, base_url: str, model: str, client: httpx.AsyncClient) -> None:
        self._base = base_url.rstrip("/")
        self.model = model
        self._client = client

    async def complete(self, system: str, messages: list[ChatMessage]) -> str:
        body = {
            "model": self.model,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0},
            "messages": [{"role": "system", "content": system}]
            + [{"role": m.role, "content": m.content} for m in messages],
        }
        try:
            response = await self._client.post(
                f"{self._base}/api/chat", json=body, timeout=REQUEST_TIMEOUT
            )
        except httpx.TimeoutException as exc:
            raise ProviderError("The AI model took too long to answer.") from exc
        except httpx.HTTPError as exc:
            raise ProviderError("Ollama isn't running on the laptop.") from exc
        if response.status_code == 404:
            raise ProviderError(
                f"The model {self.model} isn't installed. Run: ollama pull {self.model}"
            )
        if response.status_code != 200:
            raise ProviderError("Ollama couldn't answer that.")
        content = _json(response).get("message", {}).get("content")
        if not isinstance(content, str):
            raise ProviderError("The AI model sent back something unexpected.")
        return content

    async def check(self) -> str | None:
        try:
            response = await self._client.get(f"{self._base}/api/tags", timeout=CHECK_TIMEOUT)
        except httpx.HTTPError:
            return "Ollama isn't running on the laptop. Start it, or see the README for setup."
        if response.status_code != 200:
            return "Ollama isn't answering on the laptop."
        try:
            models = response.json().get("models", [])
        except ValueError:
            return "Ollama isn't answering on the laptop."
        names = {m.get("name") for m in models if isinstance(m, dict)}
        wanted = {self.model} if ":" in self.model else {self.model, f"{self.model}:latest"}
        if names.isdisjoint(wanted):
            return f"The model {self.model} isn't installed. Run: ollama pull {self.model}"
        return None


class GroqProvider:
    """Groq's OpenAI-compatible chat API (free tier, key in GROQ_API_KEY)."""

    name = "groq"

    def __init__(self, api_key: str | None, model: str, client: httpx.AsyncClient) -> None:
        self._key = api_key
        self.model = model
        self._client = client

    async def complete(self, system: str, messages: list[ChatMessage]) -> str:
        if not self._key:
            raise ProviderError("Set GROQ_API_KEY on the laptop to use Groq.")
        body = {
            "model": self.model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": system}]
            + [{"role": m.role, "content": m.content} for m in messages],
        }
        try:
            response = await self._client.post(
                GROQ_URL,
                json=body,
                headers={"Authorization": f"Bearer {self._key}"},
                timeout=REQUEST_TIMEOUT,
            )
        except httpx.TimeoutException as exc:
            raise ProviderError("Groq took too long to answer.") from exc
        except httpx.HTTPError as exc:
            raise ProviderError("Couldn't reach Groq. Check the laptop's internet.") from exc
        if response.status_code in {401, 403}:
            raise ProviderError("Groq didn't accept the API key.")
        if response.status_code == 429:
            raise ProviderError("Groq's free limit was reached. Try again in a minute.")
        if response.status_code != 200:
            raise ProviderError("Groq couldn't answer that.")
        try:
            content = _json(response)["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError("Groq sent back something unexpected.") from exc
        if not isinstance(content, str):
            raise ProviderError("Groq sent back something unexpected.")
        return content

    async def check(self) -> str | None:
        return None if self._key else "Set GROQ_API_KEY on the laptop to use Groq."


class GeminiProvider:
    """Google's Gemini API (free tier, key in GEMINI_API_KEY).

    The key goes in the ``x-goog-api-key`` header, never in the URL, so it can't end up in
    proxy or server logs.
    """

    name = "gemini"

    def __init__(self, api_key: str | None, model: str, client: httpx.AsyncClient) -> None:
        self._key = api_key
        self.model = model
        self._client = client

    async def complete(self, system: str, messages: list[ChatMessage]) -> str:
        if not self._key:
            raise ProviderError("Set GEMINI_API_KEY on the laptop to use Gemini.")
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [
                {
                    "role": "model" if m.role == "assistant" else "user",
                    "parts": [{"text": m.content}],
                }
                for m in messages
            ],
            "generationConfig": {"temperature": 0, "responseMimeType": "application/json"},
        }
        try:
            response = await self._client.post(
                GEMINI_URL.format(model=self.model),
                json=body,
                headers={"x-goog-api-key": self._key},
                timeout=REQUEST_TIMEOUT,
            )
        except httpx.TimeoutException as exc:
            raise ProviderError("Gemini took too long to answer.") from exc
        except httpx.HTTPError as exc:
            raise ProviderError("Couldn't reach Gemini. Check the laptop's internet.") from exc
        if response.status_code in {401, 403}:
            raise ProviderError("Gemini didn't accept the API key.")
        if response.status_code == 429:
            raise ProviderError("Gemini's free limit was reached. Try again in a minute.")
        if response.status_code != 200:
            raise ProviderError("Gemini couldn't answer that.")
        try:
            parts = _json(response)["candidates"][0]["content"]["parts"]
            content = "".join(p.get("text", "") for p in parts)
        except (KeyError, IndexError, TypeError, AttributeError) as exc:
            raise ProviderError("Gemini sent back something unexpected.") from exc
        return content

    async def check(self) -> str | None:
        return None if self._key else "Set GEMINI_API_KEY on the laptop to use Gemini."


def create_provider(
    config: AiConfig, client: httpx.AsyncClient, env: Mapping[str, str] | None = None
) -> ChatProvider:
    """The provider named in config. ``model`` applies to that provider; when it is left at
    the Ollama default, a cloud provider uses its own default model instead."""
    env = os.environ if env is None else env
    model_is_default = config.model == DEFAULT_OLLAMA_MODEL
    if config.provider == "groq":
        model = GROQ_DEFAULT_MODEL if model_is_default else config.model
        return GroqProvider(env.get("GROQ_API_KEY"), model, client)
    if config.provider == "gemini":
        model = GEMINI_DEFAULT_MODEL if model_is_default else config.model
        return GeminiProvider(env.get("GEMINI_API_KEY"), model, client)
    return OllamaProvider(config.ollama_url, config.model, client)
