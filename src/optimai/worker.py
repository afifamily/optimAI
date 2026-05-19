"""MLX inference client — OpenAI-style chat completions worker with KV-cache reuse.

Talks to a local `mlx_lm.server` (DEC-017) running Qwen2.5-Coder-32B-Instruct-4bit
(DEC-018) on 127.0.0.1:1337 (DEC-012). The OpenAI-compatible HTTP API is the
abstraction boundary — backend can be swapped without touching this client.

Pure transport layer for Phase 1: no retry, no streaming. Failures are raised
explicitly (DEC-008 §4 — no risky fallback).
"""

import logging
from dataclasses import dataclass

import httpx

from optimai.config import get_settings

logger = logging.getLogger(__name__)


class WorkerError(Exception):
    """Base class for worker / inference failures."""


class WorkerHTTPError(WorkerError):
    """Raised on a non-2xx HTTP response or a malformed response payload."""


class WorkerTimeout(WorkerError):
    """Raised when the HTTP request exceeds its time budget."""


@dataclass(frozen=True)
class ChatResponse:
    """Parsed result of a chat completion call."""

    content: str  # assistant message.content
    finish_reason: str  # "stop" | "length" | ...
    prompt_tokens: int
    completion_tokens: int
    cached_tokens: int  # KV-cache hits (DEC-017); 0 if not reported
    raw: dict  # raw JSON payload, kept for debugging


def _parse_response(data: dict) -> ChatResponse:
    """Extract a `ChatResponse` from the OpenAI-compatible JSON payload."""
    try:
        choice = data["choices"][0]
        content = choice["message"]["content"]
        finish_reason = choice["finish_reason"]
        usage = data["usage"]
        prompt_tokens = usage["prompt_tokens"]
        completion_tokens = usage["completion_tokens"]
    except (KeyError, IndexError, TypeError) as exc:
        raise WorkerHTTPError(f"Malformed completion payload ({exc}): {data!r}") from exc

    # cached_tokens is optional — present only on mlx-lm builds that report
    # KV-cache hits (DEC-017). Absent => 0.
    cached_tokens = 0
    details = usage.get("prompt_tokens_details")
    if isinstance(details, dict):
        cached_tokens = details.get("cached_tokens", 0) or 0

    return ChatResponse(
        content=content,
        finish_reason=finish_reason,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cached_tokens=cached_tokens,
        raw=data,
    )


async def chat(
    messages: list[dict],
    *,
    model: str | None = None,
    base_url: str | None = None,
    temperature: float = 0.0,
    max_tokens: int = 1024,
    timeout_seconds: float = 60.0,
    client: httpx.AsyncClient | None = None,
) -> ChatResponse:
    """POST a chat completion to `mlx_lm.server`, return a parsed `ChatResponse`.

    `model` / `base_url` default to the values in Settings. The endpoint hit is
    `{base_url}/chat/completions` — `base_url` already includes the `/v1` suffix
    (see MLX_SERVER_URL), so no extra prefix is added.
    """
    settings = get_settings()
    model = model or settings.optimai_model
    base_url = (base_url or settings.mlx_server_url).rstrip("/")
    url = f"{base_url}/chat/completions"

    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    last_role = messages[-1]["role"] if messages else "(none)"
    logger.info("worker.chat start: model=%s last_role=%s", model, last_role)

    owns_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=httpx.Timeout(timeout_seconds))

    try:
        response = await client.post(url, json=payload)
    except httpx.TimeoutException as exc:
        raise WorkerTimeout(f"mlx_lm.server timed out after {timeout_seconds}s") from exc
    except httpx.HTTPError as exc:
        raise WorkerError(f"HTTP transport error: {exc}") from exc
    finally:
        if owns_client:
            await client.aclose()

    if response.status_code >= 400:
        raise WorkerHTTPError(f"HTTP {response.status_code}: {response.text[:500]}")

    try:
        data = response.json()
    except ValueError as exc:
        raise WorkerError(f"Invalid JSON from mlx_lm.server: {exc}") from exc

    parsed = _parse_response(data)
    logger.info(
        "worker.chat done: prompt_tokens=%d completion_tokens=%d "
        "cached_tokens=%d finish_reason=%s",
        parsed.prompt_tokens,
        parsed.completion_tokens,
        parsed.cached_tokens,
        parsed.finish_reason,
    )
    logger.debug("worker.chat content[:200]=%r", parsed.content[:200])
    return parsed
