"""
Characterization tests for server/nlp_tools/letter.py (T3-1a).

These pin the current behavior of the module-level helpers used by the letter
generation path — token counting, context truncation, and the message
assembly of generate_letter_content — so that structural changes to this
thin-coverage module (e.g. removal of the unused _format_name helper) can be
proven not to change live behavior.

The LLM client and config manager are mocked; no network or database access.
"""

import json
import sys

import pytest
from fastapi import HTTPException

import server.nlp_tools.letter as letter_mod
from server.nlp_tools.letter import (
    _count_tokens,
    _truncate_context,
    generate_letter_content,
)
from server.schemas.grammars import LetterDraft
from server.utils.helpers import calculate_age

PROMPTS_AND_OPTIONS = {
    "prompts": {"letter": {"system": "You are a clinical letter writer."}},
    "options": {
        "general": {"num_ctx": 64, "max_tokens": 8, "top_p": 0.9},
        "letter": {"temperature": 0.42},
    },
}


class _FakeLLMClient:
    def __init__(self, response=None, exc=None):
        self.response = response
        self.exc = exc
        self.calls = []

    async def chat_with_structured_output(self, **kwargs):
        self.calls.append(kwargs)
        if self.exc is not None:
            raise self.exc
        return self.response


class _FakeEncoding:
    """Deterministic stand-in for a tiktoken encoding (1 token per 4 chars).

    Avoids the network fetch tiktoken performs on first use of an encoding,
    keeping the suite deterministic in offline environments.
    """

    def __init__(self):
        self.encode_calls = 0

    def encode(self, text, disallowed_special=()):  # noqa: ARG002 - mirrors tiktoken API
        self.encode_calls += 1
        return list(range(max(1, (len(text) + 3) // 4)) if text else [])


@pytest.fixture(autouse=True)
def fake_tiktoken(monkeypatch):
    import tiktoken

    fake_encoding = _FakeEncoding()

    def _fake_get_encoding(name):
        assert name == "cl100k_base"
        return fake_encoding

    monkeypatch.setattr(tiktoken, "get_encoding", _fake_get_encoding)
    return fake_encoding


@pytest.fixture(autouse=True)
def fake_config(monkeypatch):
    # Every test in this module drives generate_letter_content / helpers that
    # read the (global) config manager, so install a fake for all of them.
    # Tests that need different user settings override get_user_settings in the
    # body (the shared function-scoped monkeypatch applies the later setattr).
    monkeypatch.setattr(
        letter_mod.config_manager, "get_config", lambda: {"PRIMARY_MODEL": "test-llm"}
    )
    # Deep copy so tests can't mutate the module-level constant
    monkeypatch.setattr(
        letter_mod.config_manager,
        "get_prompts_and_options",
        lambda: json.loads(json.dumps(PROMPTS_AND_OPTIONS)),
    )
    monkeypatch.setattr(letter_mod.config_manager, "get_user_settings", lambda: {})


def _make_llm(monkeypatch, response=None, exc=None):
    fake = _FakeLLMClient(response=response, exc=exc)
    monkeypatch.setattr(letter_mod, "get_llm_client", lambda: fake)
    return fake


# ---------------------------------------------------------------------------
# _count_tokens
# ---------------------------------------------------------------------------


def test_count_tokens_uses_tiktoken_when_available(fake_tiktoken):
    text = "The patient presented with chest pain."
    assert _count_tokens(text) == max(1, (len(text) + 3) // 4)
    assert _count_tokens("") == 0
    assert fake_tiktoken.encode_calls == 2


def test_count_tokens_falls_back_to_len_over_4(monkeypatch):
    # Forcing `import tiktoken` to raise ImportError exercises the fallback.
    monkeypatch.setitem(sys.modules, "tiktoken", None)
    assert _count_tokens("a" * 8) == 2
    assert _count_tokens("") == 0


# ---------------------------------------------------------------------------
# _truncate_context
# ---------------------------------------------------------------------------


def test_truncate_context_empty_returns_empty():
    assert _truncate_context([], 10) == []


def test_truncate_context_within_budget_and_already_leading_assistant_unchanged():
    # When the context already starts with an assistant message and is within
    # budget, nothing is altered.
    msgs = [
        {"role": "assistant", "content": "hi there"},
        {"role": "user", "content": "thanks"},
    ]
    assert _truncate_context(msgs, 10_000) == msgs


def test_truncate_context_within_budget_still_enforces_assistant_head():
    # The "result starts with an assistant message" guarantee is applied even
    # when there is no token-budget pressure: leading non-assistant turns are
    # dropped unconditionally. This is documented behavior and an invariant any
    # refactor must preserve.
    msgs = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi there"},
    ]
    assert _truncate_context(msgs, 10_000) == [{"role": "assistant", "content": "hi there"}]


def test_truncate_context_without_assistant_is_unchanged():
    msgs = [
        {"role": "user", "content": "x" * 200},
        {"role": "user", "content": "y" * 200},
    ]
    assert _truncate_context(msgs, 1) == msgs


def test_truncate_context_drops_oldest_assistant_turn_first():
    msgs = [
        {"role": "user", "content": "u0"},
        {"role": "assistant", "content": "a1 " + "z" * 300},
        {"role": "user", "content": "u2 " + "z" * 300},
        {"role": "assistant", "content": "a3"},
    ]
    result = _truncate_context(msgs, 1)
    # The oldest assistant turn (a1) and everything up to the next assistant
    # turn (u2) must be gone; the result must start with an assistant message.
    assert all(m["content"] != "a1 " + "z" * 300 for m in result)
    assert all(m["content"] != "u2 " + "z" * 300 for m in result)
    assert result and result[0]["role"] == "assistant"
    assert result[-1]["content"] == "a3"


def test_truncate_context_result_starts_with_assistant():
    msgs = [
        {"role": "user", "content": "u0 " + "z" * 100},
        {"role": "assistant", "content": "a1 " + "z" * 100},
        {"role": "user", "content": "u2 " + "z" * 100},
        {"role": "assistant", "content": "a3"},
    ]
    result = _truncate_context(msgs, 1)
    assert result == [{"role": "assistant", "content": "a3"}]


def test_truncate_context_single_assistant_kept_and_leading_dropped():
    msgs = [
        {"role": "user", "content": "u0 " + "z" * 100},
        {"role": "user", "content": "u1 " + "z" * 100},
        {"role": "assistant", "content": "a2 " + "z" * 100},
    ]
    # No second assistant turn, so nothing can be removed; the leading
    # user messages are still trimmed so the context starts with the assistant.
    assert _truncate_context(msgs, 1) == [{"role": "assistant", "content": "a2 " + "z" * 100}]


def test_truncate_context_two_message_floor():
    msgs = [
        {"role": "user", "content": "u0 " + "z" * 100},
        {"role": "assistant", "content": "a1 " + "z" * 100},
    ]
    # With only two messages the trimming loop never runs, but the
    # assistant-start guarantee still applies.
    assert _truncate_context(msgs, 1) == [{"role": "assistant", "content": "a1 " + "z" * 100}]


# ---------------------------------------------------------------------------
# generate_letter_content
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_letter_returns_letter_and_context(monkeypatch):
    fake = _make_llm(monkeypatch, response={"content": "Dear Patient, ..."})
    context = [
        {"role": "system", "content": "must be filtered out"},
        {"role": "user", "content": "previous question"},
        {"role": "assistant", "content": "previous answer"},
    ]
    result = await generate_letter_content(
        patient_name="Smith, John",
        gender="M",
        dob="1990-01-01",
        template_data={"chief_complaint": "Chest pain", "empty_field": ""},
        context=context,
    )

    assert result["letter"] == "Dear Patient, ..."
    # The context returned to the caller is the same truncated context handed
    # to the model: system messages are filtered, and the assistant-head
    # guarantee trims the leading user turn (see _truncate_context tests).
    assert result["context"] == [{"role": "assistant", "content": "previous answer"}]

    call = fake.calls[0]
    assert call["model"] == "test-llm"
    assert call["options"]["temperature"] == 0.42  # from letter options
    assert call["options"]["num_ctx"] == 64  # from general options
    assert call["schema"] == LetterDraft.model_json_schema()

    messages = call["messages"]
    system_content = messages[0]["content"]
    assert messages[0]["role"] == "system"
    assert "You are a clinical letter writer." in system_content
    assert 'top-level key "content"' in system_content
    # No user settings configured, so no doctor-voice block
    assert "in the voice of" not in system_content

    patient_message = next(
        m for m in messages if m["role"] == "user" and "Patient Name:" in m["content"]
    )
    assert "Patient Name: Smith, John" in patient_message["content"]
    assert "Gender: M" in patient_message["content"]
    assert f"Age: {calculate_age('1990-01-01')}" in patient_message["content"]
    assert "Chief Complaint:\nChest pain" in patient_message["content"]
    # Falsy template values are skipped
    assert "Empty Field" not in patient_message["content"]


@pytest.mark.asyncio
async def test_generate_letter_accepts_json_string_response(monkeypatch):
    _make_llm(monkeypatch, response=json.dumps({"content": "Hello from string"}))
    result = await generate_letter_content(
        patient_name="Doe, Jane",
        gender="F",
        dob="1985-05-05",
        template_data={"summary": "Routine check"},
    )
    assert result["letter"] == "Hello from string"
    assert result["context"] == []


@pytest.mark.asyncio
async def test_generate_letter_additional_instruction_inserted(monkeypatch):
    fake = _make_llm(monkeypatch, response={"content": "ok"})
    await generate_letter_content(
        patient_name="Doe, Jane",
        gender="F",
        dob="1985-05-05",
        template_data={"summary": "x"},
        additional_instruction="Please be brief.",
    )
    messages = fake.calls[0]["messages"]
    instruction = next(m for m in messages if "additional instructions" in m.get("content", ""))
    patient_idx = next(i for i, m in enumerate(messages) if "Patient Name:" in m.get("content", ""))
    instruction_idx = next(
        i for i, m in enumerate(messages) if "additional instructions" in m.get("content", "")
    )
    assert instruction_idx < patient_idx
    assert "Please be brief." in instruction["content"]


@pytest.mark.asyncio
async def test_generate_letter_doctor_context_added(monkeypatch):
    monkeypatch.setattr(
        letter_mod.config_manager,
        "get_user_settings",
        lambda: {"name": "Dr. Rahimi", "specialty": "Cardiology"},
    )
    fake = _make_llm(monkeypatch, response={"content": "ok"})
    await generate_letter_content(
        patient_name="Doe, Jane", gender="F", dob="1985-05-05", template_data={}
    )
    system_content = fake.calls[0]["messages"][0]["content"]
    assert "Write the letter in the voice of Dr. Rahimi, a Cardiology specialist." in system_content


@pytest.mark.asyncio
async def test_generate_letter_llm_error_raises_http_500(monkeypatch):
    _make_llm(monkeypatch, exc=RuntimeError("boom"))
    with pytest.raises(HTTPException) as excinfo:
        await generate_letter_content(
            patient_name="Doe, Jane", gender="F", dob="1985-05-05", template_data={}
        )
    assert excinfo.value.status_code == 500
    assert "Error generating letter content" in excinfo.value.detail
