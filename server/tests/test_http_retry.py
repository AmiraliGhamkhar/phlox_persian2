"""Tests for bounded AI-provider retries and request correlation."""

from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from server.middleware import RequestIdMiddleware
from server.utils.http_retry import (
    ProviderHTTPError,
    sanitize_provider_error,
    with_retries,
)
from server.utils.request_context import normalize_request_id


@pytest.mark.asyncio
async def test_with_retries_retries_429_then_succeeds(monkeypatch):
    monkeypatch.setattr("server.utils.http_retry.asyncio.sleep", AsyncMock())
    calls = {"n": 0}

    async def operation():
        calls["n"] += 1
        if calls["n"] < 3:
            raise ProviderHTTPError("rate limited", status_code=429)
        return "ok"

    assert await with_retries(operation, operation_name="test") == "ok"
    assert calls["n"] == 3


@pytest.mark.asyncio
async def test_with_retries_does_not_retry_400():
    calls = {"n": 0}

    async def operation():
        calls["n"] += 1
        raise ProviderHTTPError("bad request", status_code=400)

    with pytest.raises(ProviderHTTPError) as excinfo:
        await with_retries(operation, operation_name="test")
    assert excinfo.value.status_code == 400
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_with_retries_gives_up_after_max(monkeypatch):
    monkeypatch.setattr("server.utils.http_retry.asyncio.sleep", AsyncMock())
    calls = {"n": 0}

    async def operation():
        calls["n"] += 1
        raise ProviderHTTPError("unavailable", status_code=503)

    with pytest.raises(ProviderHTTPError):
        await with_retries(operation, operation_name="test")
    assert calls["n"] == 3  # initial + 2 retries


def test_sanitize_provider_error_redacts_keys():
    leaked = "invalid key sk-abcdefghijklmnopqrstuvwxyz Authorization: Bearer supersecret"
    cleaned = sanitize_provider_error(leaked)
    assert "sk-abcdefghijklmnopqrstuvwxyz" not in cleaned
    assert "supersecret" not in cleaned
    assert "[redacted]" in cleaned


def test_normalize_request_id_rejects_unsafe_values():
    assert normalize_request_id("abc-123") == "abc-123"
    assert normalize_request_id("not a valid id!") is None
    assert normalize_request_id("") is None
    assert normalize_request_id("x" * 80) is None


def test_request_id_middleware_echoes_and_generates():
    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)

    @app.get("/ping")
    async def ping(request: Request):
        return {"id": request.state.request_id}

    client = TestClient(app)
    echoed = client.get("/ping", headers={"X-Request-Id": "trace-42"})
    assert echoed.headers["X-Request-Id"] == "trace-42"
    assert echoed.json()["id"] == "trace-42"

    generated = client.get("/ping")
    assert generated.headers["X-Request-Id"]
    assert generated.json()["id"] == generated.headers["X-Request-Id"]
