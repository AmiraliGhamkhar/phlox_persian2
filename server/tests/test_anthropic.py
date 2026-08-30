"""Tests for the native Anthropic Messages adapter."""

from typing import Any, cast

import pytest

from server.llm_client.providers.anthropic import convert_messages, convert_tools


def test_convert_messages_extracts_system_and_tools():
    system, messages = convert_messages(
        [
            {"role": "system", "content": "You are a scribe."},
            {"role": "user", "content": "Hello"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "function": {"name": "lookup", "arguments": '{"q": "hbA1c"}'},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "call_1", "content": "7.2"},
        ]
    )
    assert "scribe" in system
    assert messages[0]["role"] == "user"
    assert messages[1]["content"][0]["type"] == "tool_use"
    assert messages[2]["content"][0]["type"] == "tool_result"
    assert messages[1]["content"][0]["input"]["q"] == "hbA1c"


def test_convert_messages_merges_consecutive_tool_results():
    _system, messages = convert_messages(
        [
            {"role": "user", "content": "run both"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": "c1", "function": {"name": "a", "arguments": "{}"}},
                    {"id": "c2", "function": {"name": "b", "arguments": "{}"}},
                ],
            },
            {"role": "tool", "tool_call_id": "c1", "content": "one"},
            {"role": "tool", "tool_call_id": "c2", "content": "two"},
        ]
    )
    assert len(messages) == 3
    assert messages[2]["role"] == "user"
    assert [block["tool_use_id"] for block in messages[2]["content"]] == ["c1", "c2"]


def test_convert_messages_keeps_vision_blocks():
    from server.llm_client.providers.anthropic import convert_messages

    _system, messages = convert_messages(
        [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "read this"},
                    {
                        "type": "image_url",
                        "image_url": {"url": "data:image/png;base64,abcd"},
                    },
                ],
            }
        ]
    )
    assert messages[0]["content"][0]["type"] == "text"
    assert messages[0]["content"][1]["type"] == "image"
    assert messages[0]["content"][1]["source"]["data"] == "abcd"
    assert messages[0]["content"][1]["source"]["media_type"] == "image/png"


def test_convert_messages_keeps_http_image_url():
    from server.llm_client.providers.anthropic import convert_messages

    _system, messages = convert_messages(
        [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": "https://example.com/scan.png"},
                    }
                ],
            }
        ]
    )
    assert messages[0]["content"][0]["source"]["type"] == "url"
    assert messages[0]["content"][0]["source"]["url"] == "https://example.com/scan.png"


def test_convert_tools_maps_openai_functions():
    tools = convert_tools(
        [
            {
                "type": "function",
                "function": {
                    "name": "search",
                    "description": "Search notes",
                    "parameters": {"type": "object", "properties": {"q": {"type": "string"}}},
                },
            }
        ]
    )
    assert tools is not None
    assert tools[0]["name"] == "search"
    assert tools[0]["input_schema"]["properties"]["q"]["type"] == "string"


@pytest.mark.asyncio
async def test_anthropic_nonstream_chat(monkeypatch):
    from server.llm_client.providers import anthropic as anthropic_mod

    class FakeResponse:
        status_code = 200
        text = "{}"

        def json(self):
            return {
                "content": [{"type": "text", "text": "سلام بیمار HbA1c 7.2 دارد"}],
            }

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, json=None, headers=None):
            assert url.endswith("/v1/messages")
            assert headers is not None
            assert json is not None
            assert headers["x-api-key"] == "sk-ant-test"
            assert json["model"] == "claude-haiku-4-5"
            return FakeResponse()

    monkeypatch.setattr(anthropic_mod.httpx, "AsyncClient", FakeClient)
    result = await anthropic_mod.anthropic_chat(
        "https://api.anthropic.com",
        "sk-ant-test",
        "claude-haiku-4-5",
        [{"role": "user", "content": "hi"}],
    )
    assert isinstance(result, dict)
    payload = cast("dict[str, Any]", result)
    assert "HbA1c" in payload["message"]["content"]
