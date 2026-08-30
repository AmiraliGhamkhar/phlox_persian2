"""Per-request context that must never carry PHI.

``request_id`` is a correlation token for logs and the ``X-Request-Id``
response header. It is stored in a ContextVar so async tasks spawned by
the same request inherit it without threading it through every call.
"""

from __future__ import annotations

import re
from contextvars import ContextVar, Token

_request_id: ContextVar[str] = ContextVar("request_id", default="-")
_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


def get_request_id() -> str:
    """Return the current request id, or ``-`` outside a request."""
    return _request_id.get() or "-"


def set_request_id(value: str) -> Token[str]:
    """Bind a request id to the current task. Caller must ``reset`` the token."""
    return _request_id.set(value or "-")


def reset_request_id(token: Token[str]) -> None:
    """Restore the previous request id after a request finishes."""
    _request_id.reset(token)


def normalize_request_id(incoming: str | None) -> str | None:
    """Accept a client-supplied id only when it is a short safe token."""
    value = (incoming or "").strip()
    if value and _VALID_REQUEST_ID.match(value):
        return value
    return None
