"""Configurable AI provider interfaces and local/HTTP implementations."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from researchhub_ai.embeddings import Encoder, get_embedding_service

logger = logging.getLogger(__name__)
_OLLAMA_PROVIDERS: dict[tuple[object, ...], OllamaAIProvider] = {}


class OllamaQueueTimeout(RuntimeError):
    """Raised when the single local generation slot cannot be acquired."""


class OllamaResourceError(RuntimeError):
    """Raised when Ollama reports insufficient memory."""


@dataclass(frozen=True)
class TextGeneration:
    text: str
    model: str
    provider: str
    prompt_tokens: int = 0
    completion_tokens: int = 0


class AIProvider(Protocol):
    name: str

    async def generate_text(
        self, prompt: str, *, model: str | None = None, options: dict[str, Any] | None = None
    ) -> TextGeneration: ...
    async def generate_chat_response(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        options: dict[str, Any] | None = None,
    ) -> TextGeneration: ...
    async def generate_embeddings(self, texts: list[str]) -> list[list[float]]: ...
    async def health_check(self) -> bool: ...
    async def list_models(self) -> list[str]: ...


class LocalAIProvider:
    """Offline embeddings plus conservative extractive text fallback."""

    name = "local"

    def __init__(self, embedding_model: str, device: str = "cpu") -> None:
        self.embedding_model = embedding_model
        self.encoder: Encoder = get_embedding_service(embedding_model, device)

    async def generate_text(
        self, prompt: str, *, model: str | None = None, options: dict[str, Any] | None = None
    ) -> TextGeneration:
        del options
        clean = " ".join(prompt.split())
        text = clean[:1200] if clean else "No grounded source text was supplied."
        return TextGeneration(text=text, model=model or "grounded-local-v1", provider=self.name)

    async def generate_chat_response(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        options: dict[str, Any] | None = None,
    ) -> TextGeneration:
        prompt = next(
            (item["content"] for item in reversed(messages) if item.get("role") == "user"), ""
        )
        return await self.generate_text(prompt, model=model, options=options)

    async def generate_embeddings(self, texts: list[str]) -> list[list[float]]:
        return self.encoder.encode_documents(texts)

    async def health_check(self) -> bool:
        return True

    async def list_models(self) -> list[str]:
        return [self.embedding_model, "grounded-local-v1"]


class OllamaAIProvider:
    name = "ollama"

    def __init__(
        self,
        base_url: str,
        default_model: str,
        timeout: float,
        *,
        queue_timeout: float = 120,
        max_concurrent: int = 1,
        max_num_ctx: int = 4096,
        max_num_predict: int = 600,
        keep_alive: str = "5m",
        default_options: dict[str, Any] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.default_model = default_model
        self.timeout = timeout
        self.queue_timeout = queue_timeout
        self.max_num_ctx = max_num_ctx
        self.max_num_predict = max_num_predict
        self.keep_alive = keep_alive
        self.default_options = default_options or {}
        self._client = httpx.AsyncClient(timeout=_http_timeout(timeout))
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def generate_text(
        self, prompt: str, *, model: str | None = None, options: dict[str, Any] | None = None
    ) -> TextGeneration:
        payload = {
            "model": model or self.default_model,
            "prompt": prompt,
            "stream": False,
            "keep_alive": self.keep_alive,
            "options": self._options(options),
        }
        data = await self._post("/api/generate", payload)
        return TextGeneration(
            text=str(data.get("response", "")),
            model=str(data.get("model", payload["model"])),
            provider=self.name,
            prompt_tokens=int(data.get("prompt_eval_count", 0)),
            completion_tokens=int(data.get("eval_count", 0)),
        )

    async def generate_chat_response(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        options: dict[str, Any] | None = None,
    ) -> TextGeneration:
        payload = {
            "model": model or self.default_model,
            "messages": messages,
            "stream": False,
            "keep_alive": self.keep_alive,
            "options": self._options(options),
        }
        data = await self._post("/api/chat", payload)
        raw_message = data.get("message")
        message: dict[str, Any] = raw_message if isinstance(raw_message, dict) else {}
        return TextGeneration(
            text=str(message.get("content", "")),
            model=str(data.get("model", payload["model"])),
            provider=self.name,
            prompt_tokens=int(data.get("prompt_eval_count", 0)),
            completion_tokens=int(data.get("eval_count", 0)),
        )

    async def generate_embeddings(self, texts: list[str]) -> list[list[float]]:
        data = await self._post("/api/embed", {"model": self.default_model, "input": texts})
        vectors = data.get("embeddings")
        if not isinstance(vectors, list):
            raise RuntimeError("Ollama returned no embeddings")
        return vectors

    async def health_check(self) -> bool:
        try:
            return (await self._client.get(f"{self.base_url}/api/tags")).is_success
        except httpx.HTTPError:
            return False

    async def list_models(self) -> list[str]:
        response = await self._client.get(f"{self.base_url}/api/tags")
        response.raise_for_status()
        return [
            str(item["name"])
            for item in response.json().get("models", [])
            if isinstance(item, dict) and item.get("name")
        ]

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        started = asyncio.get_running_loop().time()
        try:
            await asyncio.wait_for(self._semaphore.acquire(), timeout=self.queue_timeout)
        except TimeoutError as exc:
            raise OllamaQueueTimeout("The local AI generation queue is currently full") from exc
        waited = asyncio.get_running_loop().time() - started
        try:
            inference_started = asyncio.get_running_loop().time()
            response = await self._client.post(f"{self.base_url}{path}", json=payload)
            if response.status_code >= 400 and _is_oom(response.text):
                raise OllamaResourceError("Local AI resources are temporarily insufficient")
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict):
                raise RuntimeError("Ollama returned a malformed response")
            logger.info(
                "ollama_generation queue_wait_ms=%d inference_ms=%d prompt_tokens=%s generated_tokens=%s",
                round(waited * 1000),
                round((asyncio.get_running_loop().time() - inference_started) * 1000),
                data.get("prompt_eval_count"),
                data.get("eval_count"),
            )
            return data
        finally:
            self._semaphore.release()

    def _options(self, requested: dict[str, Any] | None) -> dict[str, Any]:
        options = {**self.default_options, **(requested or {})}
        options["num_ctx"] = min(int(options.get("num_ctx", self.max_num_ctx)), self.max_num_ctx)
        options["num_predict"] = min(
            int(options.get("num_predict", self.max_num_predict)), self.max_num_predict
        )
        return options


class OpenAICompatibleProvider:
    name = "openai-compatible"

    def __init__(self, base_url: str, api_key: str, default_model: str, timeout: float) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.default_model = default_model
        self.timeout = timeout

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"}

    async def generate_text(
        self, prompt: str, *, model: str | None = None, options: dict[str, Any] | None = None
    ) -> TextGeneration:
        return await self.generate_chat_response(
            [{"role": "user", "content": prompt}], model=model, options=options
        )

    async def generate_chat_response(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        options: dict[str, Any] | None = None,
    ) -> TextGeneration:
        del options
        async with httpx.AsyncClient(
            timeout=_http_timeout(self.timeout), headers=self.headers
        ) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                json={
                    "model": model or self.default_model,
                    "messages": messages,
                    "temperature": 0.1,
                },
            )
            response.raise_for_status()
            data = response.json()
        usage = data.get("usage", {})
        return TextGeneration(
            text=str(data["choices"][0]["message"]["content"]),
            model=str(data.get("model", model or self.default_model)),
            provider=self.name,
            prompt_tokens=int(usage.get("prompt_tokens", 0)),
            completion_tokens=int(usage.get("completion_tokens", 0)),
        )

    async def generate_embeddings(self, texts: list[str]) -> list[list[float]]:
        async with httpx.AsyncClient(
            timeout=_http_timeout(self.timeout), headers=self.headers
        ) as client:
            response = await client.post(
                f"{self.base_url}/embeddings", json={"model": self.default_model, "input": texts}
            )
            response.raise_for_status()
            data = response.json()
        return [item["embedding"] for item in data.get("data", [])]

    async def health_check(self) -> bool:
        try:
            return bool(await self.list_models())
        except httpx.HTTPError:
            return False

    async def list_models(self) -> list[str]:
        async with httpx.AsyncClient(
            timeout=_http_timeout(self.timeout), headers=self.headers
        ) as client:
            response = await client.get(f"{self.base_url}/models")
            response.raise_for_status()
            return [str(item["id"]) for item in response.json().get("data", []) if item.get("id")]


def create_ai_provider(
    provider: str,
    *,
    embedding_model: str,
    device: str = "cpu",
    chat_model: str = "",
    timeout: float = 120,
    ollama_base_url: str = "http://ollama:11434",
    openai_base_url: str | None = None,
    openai_api_key: str | None = None,
    ollama_queue_timeout: float = 120,
    ollama_max_concurrent: int = 1,
    ollama_max_num_ctx: int = 4096,
    ollama_max_num_predict: int = 600,
    ollama_keep_alive: str = "5m",
    ollama_options: dict[str, Any] | None = None,
) -> AIProvider:
    normalized = provider.casefold().strip()
    if normalized == "local":
        return LocalAIProvider(embedding_model, device)
    if normalized == "ollama":
        if not chat_model:
            raise ValueError("AI_CHAT_MODEL is required for Ollama")
        option_items = tuple(sorted((ollama_options or {}).items()))
        key = (
            ollama_base_url,
            chat_model,
            timeout,
            ollama_queue_timeout,
            ollama_max_concurrent,
            ollama_max_num_ctx,
            ollama_max_num_predict,
            ollama_keep_alive,
            option_items,
        )
        if key not in _OLLAMA_PROVIDERS:
            _OLLAMA_PROVIDERS[key] = OllamaAIProvider(
                ollama_base_url,
                chat_model,
                timeout,
                queue_timeout=ollama_queue_timeout,
                max_concurrent=ollama_max_concurrent,
                max_num_ctx=ollama_max_num_ctx,
                max_num_predict=ollama_max_num_predict,
                keep_alive=ollama_keep_alive,
                default_options=ollama_options,
            )
        return _OLLAMA_PROVIDERS[key]
    if normalized in {"openai", "openai-compatible"}:
        if not openai_base_url or not openai_api_key or not chat_model:
            raise ValueError("OpenAI-compatible provider requires base URL, API key, and model")
        return OpenAICompatibleProvider(openai_base_url, openai_api_key, chat_model, timeout)
    raise ValueError(f"Unsupported AI provider: {provider}")


def _http_timeout(seconds: float) -> httpx.Timeout:
    """Keep model generation bounded while failing fast on unavailable hosts."""

    return httpx.Timeout(seconds, connect=min(5.0, seconds))


def _is_oom(message: str) -> bool:
    lowered = message.casefold()
    return any(
        marker in lowered
        for marker in (
            "out of memory",
            "insufficient memory",
            "cannot allocate memory",
            "cuda out of memory",
        )
    )
