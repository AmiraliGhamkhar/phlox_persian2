"""Normalize streamed LLM tool-call deltas into complete tool calls."""

from __future__ import annotations

import json
from typing import Any


def tool_function_name(tool_call: dict[str, Any] | None) -> str:
    """Return the function name from an OpenAI-style tool call dict."""
    if not isinstance(tool_call, dict):
        return ""
    function = tool_call.get("function")
    if isinstance(function, dict):
        return str(function.get("name") or "").strip()
    return ""


def tool_call_id(tool_call: dict[str, Any] | None) -> str:
    """Return the provider tool-call id, or an empty string."""
    if not isinstance(tool_call, dict):
        return ""
    return str(tool_call.get("id") or "")


def parse_tool_arguments(tool_call: dict[str, Any] | None) -> dict[str, Any]:
    """Parse tool-call arguments into a dict (empty on failure)."""
    if not isinstance(tool_call, dict):
        return {}
    raw = (tool_call.get("function") or {}).get("arguments", "") or ""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _stringify_arguments(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value)
    except (TypeError, ValueError):
        return str(value)


def accumulate_tool_call(accumulated: dict[int, dict[str, Any]], tc: Any) -> None:
    """Merge a streamed tool-call delta into ``accumulated`` keyed by index.

    OpenAI streams ``ChoiceDeltaToolCall`` objects with a stable ``index``.
    Anthropic/Ollama typically yield complete dicts (sometimes with ``index``).
    """
    if isinstance(tc, dict):
        raw_idx = tc.get("index")
        idx = raw_idx if isinstance(raw_idx, int) else len(accumulated)
        function_payload = tc.get("function") or {}
        if not isinstance(function_payload, dict):
            function_payload = {}
        name_part = function_payload.get("name") or ""
        args_part = _stringify_arguments(function_payload.get("arguments", ""))

        if idx not in accumulated:
            accumulated[idx] = {
                "id": tc.get("id") or "",
                "type": tc.get("type") or "function",
                "function": {"name": "", "arguments": ""},
            }
        if name_part:
            accumulated[idx]["function"]["name"] += name_part
        if args_part:
            accumulated[idx]["function"]["arguments"] += args_part
        if tc.get("id"):
            accumulated[idx]["id"] = tc.get("id")
        if tc.get("type"):
            accumulated[idx]["type"] = tc.get("type")
        return

    if hasattr(tc, "index"):
        idx = tc.index
        if idx not in accumulated:
            accumulated[idx] = {
                "id": getattr(tc, "id", "") or "",
                "type": getattr(tc, "type", "function") or "function",
                "function": {"name": "", "arguments": ""},
            }
        function = getattr(tc, "function", None)
        if function is not None:
            name_part = getattr(function, "name", None)
            args_part = getattr(function, "arguments", None)
            if name_part:
                accumulated[idx]["function"]["name"] += name_part
            if args_part:
                accumulated[idx]["function"]["arguments"] += args_part
        call_id = getattr(tc, "id", None)
        if call_id:
            accumulated[idx]["id"] = call_id
        call_type = getattr(tc, "type", None)
        if call_type:
            accumulated[idx]["type"] = call_type


def finalized_tool_calls(accumulated: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
    """Return complete tool calls in index order, dropping nameless fragments."""
    calls = [value for _, value in sorted(accumulated.items())]
    return [call for call in calls if tool_function_name(call)]
