"""Tests for optimai.worker — mocked with httpx.MockTransport (no extra dep)."""

import httpx
import pytest

from optimai.worker import (
    WorkerError,
    WorkerHTTPError,
    WorkerTimeout,
    chat,
)

BASE_URL = "http://test-mlx/v1"


def _completion(
    content: str = "hello",
    finish_reason: str = "stop",
    prompt_tokens: int = 33,
    completion_tokens: int = 4,
    cached_tokens: int | None = None,
) -> dict:
    """Build an OpenAI-compatible chat completion payload."""
    usage: dict = {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
    }
    if cached_tokens is not None:
        usage["prompt_tokens_details"] = {"cached_tokens": cached_tokens}
    return {
        "choices": [
            {"message": {"role": "assistant", "content": content}, "finish_reason": finish_reason}
        ],
        "usage": usage,
    }


def _client(handler) -> httpx.AsyncClient:
    """Build an AsyncClient backed by a MockTransport handler."""
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_happy_path():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_completion(content="WORKER_OK"))

    async with _client(handler) as client:
        response = await chat(
            [{"role": "user", "content": "hi"}],
            model="test-model",
            base_url=BASE_URL,
            client=client,
        )
    assert response.content == "WORKER_OK"
    assert response.finish_reason == "stop"
    assert response.prompt_tokens == 33
    assert response.completion_tokens == 4


async def test_cached_tokens_extracted_when_present():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_completion(cached_tokens=21))

    async with _client(handler) as client:
        response = await chat(
            [{"role": "user", "content": "hi"}], base_url=BASE_URL, client=client
        )
    assert response.cached_tokens == 21


async def test_cached_tokens_defaults_to_zero_when_absent():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_completion(cached_tokens=None))

    async with _client(handler) as client:
        response = await chat(
            [{"role": "user", "content": "hi"}], base_url=BASE_URL, client=client
        )
    assert response.cached_tokens == 0


async def test_http_500_raises_worker_http_error():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="internal error")

    async with _client(handler) as client:
        with pytest.raises(WorkerHTTPError):
            await chat([{"role": "user", "content": "hi"}], base_url=BASE_URL, client=client)


async def test_network_timeout_raises_worker_timeout():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timed out", request=request)

    async with _client(handler) as client:
        with pytest.raises(WorkerTimeout):
            await chat([{"role": "user", "content": "hi"}], base_url=BASE_URL, client=client)


async def test_payload_without_choices_raises_worker_error():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"usage": {"prompt_tokens": 1, "completion_tokens": 1}})

    async with _client(handler) as client:
        with pytest.raises(WorkerError):
            await chat([{"role": "user", "content": "hi"}], base_url=BASE_URL, client=client)


async def test_invalid_json_raises_worker_error():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not json at all")

    async with _client(handler) as client:
        with pytest.raises(WorkerError):
            await chat([{"role": "user", "content": "hi"}], base_url=BASE_URL, client=client)


async def test_unicode_round_trip():
    sent: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        sent["body"] = json.loads(request.content)
        return httpx.Response(200, json=_completion(content="réponse arabe: مرحبا"))

    async with _client(handler) as client:
        response = await chat(
            [{"role": "user", "content": "français: éàù — arabe: السلام"}],
            base_url=BASE_URL,
            client=client,
        )
    assert response.content == "réponse arabe: مرحبا"
    assert sent["body"]["messages"][0]["content"] == "français: éàù — arabe: السلام"


async def test_endpoint_url_has_no_double_v1():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, json=_completion())

    async with _client(handler) as client:
        await chat(
            [{"role": "user", "content": "hi"}],
            base_url="http://test-mlx/v1",
            client=client,
        )
    # base_url already ends in /v1 — must not become /v1/v1/.
    assert seen["url"] == "http://test-mlx/v1/chat/completions"


async def test_request_carries_model_and_messages():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=_completion())

    async with _client(handler) as client:
        await chat(
            [{"role": "user", "content": "hi"}],
            model="my-model",
            base_url=BASE_URL,
            client=client,
        )
    assert seen["body"]["model"] == "my-model"
    assert seen["body"]["temperature"] == 0.0
    assert seen["body"]["messages"] == [{"role": "user", "content": "hi"}]
