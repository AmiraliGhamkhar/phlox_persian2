"""Bounded retries for transient AI-provider failures.

Retries 429, 5xx, timeouts, and network errors. Never retries other 4xx
(client/configuration problems). Cap is two retries (three attempts) with
exponential backoff. Infinite loops are impossible by construction.
"""

from __future__ import annotations

import asyncio
import logging
import random
import re
from typing import TYPE_CHECKING, TypeVar

import httpx

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

from server.utils.request_context import get_request_id

logger = logging.getLogger(__name__)

T = TypeVar("T")

MAX_RETRIES = 2
BASE_DELAY_SECONDS = 0.4
MAX_DELAY_SECONDS = 4.0

_SECRET_RE = re.compile(
    r"(sk-[A-Za-z0-9_\-]{8,}|Bearer\s+\S+|x-api-key['\"\s:=]+[\w\-]+)",
    re.IGNORECASE,
)


class ProviderHTTPError(ValueError):
    """Provider HTTP failure with a status code the retry policy can inspect."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


def sanitize_provider_error(body: str, limit: int = 240) -> str:
    """Redact secrets and truncate provider error bodies before they leave this layer."""
    text = _SECRET_RE.sub("[redacted]", body or "")
    text = " ".join(text.split())
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


def is_retryable_status(status: int | None) -> bool:
    if status is None:
        return False
    return status == 429 or status >= 500


def is_retryable_exception(exc: BaseException) -> bool:
    if isinstance(
        exc,
        (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError, httpx.ConnectError),
    ):
        return True
    status = getattr(exc, "status_code", None)
    if status is None:
        status = getattr(getattr(exc, "response", None), "status_code", None)
    return is_retryable_status(status)


def _retry_after_seconds(exc: BaseException) -> float | None:
    response = getattr(exc, "response", None)
    if response is None:
        return None
    headers = getattr(response, "headers", None) or {}
    raw = headers.get("retry-after") or headers.get("Retry-After")
    if not raw:
        return None
    try:
        return min(MAX_DELAY_SECONDS, max(0.0, float(raw)))
    except (TypeError, ValueError):
        return None


async def with_retries(  # noqa: UP047 (kept TypeVar-based for Python 3.11 parseability)
    operation: Callable[[], Awaitable[T]],
    *,
    operation_name: str = "ai",
    max_retries: int = MAX_RETRIES,
) -> T:
    """Run ``operation`` with bounded exponential backoff on transient failures."""
    last_error: BaseException | None = None
    for attempt in range(max_retries + 1):
        try:
            result = await operation()
            if attempt:
                logger.info(
                    "ai_retry_succeeded operation=%s attempt=%s request_id=%s",
                    operation_name,
                    attempt + 1,
                    get_request_id(),
                )
            return result
        except Exception as exc:
            last_error = exc
            if attempt >= max_retries or not is_retryable_exception(exc):
                raise
            delay = min(MAX_DELAY_SECONDS, BASE_DELAY_SECONDS * (2**attempt))
            delay += random.uniform(0, delay * 0.2)
            retry_after = _retry_after_seconds(exc)
            if retry_after is not None:
                delay = min(MAX_DELAY_SECONDS, max(delay, retry_after))
            logger.warning(
                "ai_retry operation=%s attempt=%s/%s delay=%.2f status=%s request_id=%s",
                operation_name,
                attempt + 1,
                max_retries + 1,
                delay,
                getattr(exc, "status_code", None),
                get_request_id(),
            )
            await asyncio.sleep(delay)
    assert last_error is not None
    raise last_error
