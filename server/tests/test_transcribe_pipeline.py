"""Characterization tests for the ambient-note transcription pipeline (T3-2).

Files under test:
- ``server/transcription/text.py``  (``process_transcription`` + prompt assembly)
- ``server/api/transcribe.py``      (``/api/transcribe/*`` endpoint contracts)

These pin the current behavior so that a structural refactor of this
thin-coverage path can be proven not to change live behavior. Invariants
protected here:

- #2 (request path): the endpoint delegates to the domain layer
  (``process_transcription`` → ``get_llm_client``); nothing is re-implemented
  in the route.
- #5 (no PHI egress): this path is pure LLM. A test asserts the module
  imports no external-search / egress clients (PubMed / Wikipedia / MCP /
  raw HTTP), so a future import cannot silently add an egress channel.

All LLM, ASR, and database access is mocked — no network, no real DB.
"""

import inspect
import json
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import server.api.transcribe as transcribe_mod
import server.transcription.text as text_mod
from server.transcription.text import (
    _build_patient_context,
    _capitalize_first_char,
    process_transcription,
)

# ---------------------------------------------------------------------------
# Shared fakes
# ---------------------------------------------------------------------------

GENERAL_OPTIONS = {"num_ctx": 64, "max_tokens": 8, "top_p": 0.9}
PROMPTS_AND_OPTIONS = {
    "prompts": {},
    "options": {"general": GENERAL_OPTIONS},
}


class _FakeLLMClient:
    """Records calls and returns a canned structured-output response."""

    def __init__(self, response: str | None = None, exc: Exception | None = None):
        self.response = response
        self.exc = exc
        self.calls: list[dict] = []

    async def chat(self, **kwargs):
        self.calls.append(kwargs)
        if self.exc is not None:
            raise self.exc
        assert self.response is not None
        return {"message": {"content": self.response}}


def _make_field(key: str, persistent: bool = False) -> "object":
    from server.schemas.templates import TemplateField

    return TemplateField(
        field_key=key,
        field_name=f"Field {key}",
        field_type="text",
        persistent=persistent,
        system_prompt=f"Instructions for {key}.",
        style_example="Example.",
    )


def _multi_field_json(summaries: dict) -> str:
    return json.dumps({"field_summaries": summaries})


@pytest.fixture(autouse=True)
def fake_config(monkeypatch):
    from server.database.config import manager as config_manager_mod

    monkeypatch.setattr(
        config_manager_mod.config_manager,
        "get_config",
        lambda: {"PRIMARY_MODEL": "test-model"},
    )
    monkeypatch.setattr(
        config_manager_mod.config_manager,
        "get_prompts_and_options",
        lambda: PROMPTS_AND_OPTIONS,
    )


@pytest.fixture(autouse=True)
def fake_refine(monkeypatch):
    """Identity refinement so the test isolates the aggregation logic."""

    async def _refine(content, field, is_ambient=True):  # noqa: ARG001 - mirrors refine_field_content API
        return content

    monkeypatch.setattr(text_mod, "refine_field_content", _refine)


# ---------------------------------------------------------------------------
# text.py — process_transcription unit contracts
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_only_non_persistent_fields_are_processed(monkeypatch):
    client = _FakeLLMClient(_multi_field_json({"nonp": ["a point"]}))
    monkeypatch.setattr(text_mod, "get_llm_client", lambda: client)

    fields = [_make_field("p1", persistent=True), _make_field("nonp", persistent=False)]
    result = await process_transcription("A transcript.", fields, {"name": "Doe, John"})

    # Persistent fields are filtered out before the LLM call.
    assert list(result["fields"].keys()) == ["nonp"]
    system_prompt = client.calls[0]["messages"][0]["content"]
    assert "FIELD: nonp" in system_prompt
    assert "FIELD: p1" not in system_prompt


@pytest.mark.asyncio
async def test_all_fields_sent_in_single_llm_call(monkeypatch):
    client = _FakeLLMClient(_multi_field_json({"a": ["x"], "b": ["y"], "c": ["z"]}))
    monkeypatch.setattr(text_mod, "get_llm_client", lambda: client)

    fields = [_make_field(k) for k in ("a", "b", "c")]
    result = await process_transcription("A transcript.", fields, {"name": "Doe, John"})

    # One call carries every field (not one call per field).
    assert len(client.calls) == 1
    system_prompt = client.calls[0]["messages"][0]["content"]
    for key in ("a", "b", "c"):
        assert f"FIELD: {key}" in system_prompt
    assert set(result["fields"].keys()) == {"a", "b", "c"}


@pytest.mark.asyncio
async def test_result_shape_and_duration(monkeypatch):
    client = _FakeLLMClient(_multi_field_json({"a": ["one", "two"]}))
    monkeypatch.setattr(text_mod, "get_llm_client", lambda: client)

    result = await process_transcription("A transcript.", [_make_field("a")], {"name": "Doe, John"})

    assert set(result.keys()) == {"fields", "process_duration"}
    # Bullet formatting + capitalization of each key point.
    assert result["fields"]["a"] == "• One\n• Two"
    assert isinstance(result["process_duration"], float)
    assert result["process_duration"] >= 0.0


@pytest.mark.asyncio
async def test_ambient_vs_dictate_intro(monkeypatch):
    client = _FakeLLMClient(_multi_field_json({"a": ["x"]}))
    monkeypatch.setattr(text_mod, "get_llm_client", lambda: client)

    await process_transcription(
        "t", [_make_field("a")], {}, is_ambient=True, primary_condition=None
    )
    ambient_prompt = client.calls[0]["messages"][0]["content"]

    client.calls.clear()
    await process_transcription(
        "t", [_make_field("a")], {}, is_ambient=False, primary_condition=None
    )
    dictate_prompt = client.calls[0]["messages"][0]["content"]

    assert "medical transcript" in ambient_prompt
    assert "direct dictation" in dictate_prompt
    assert "direct dictation" not in ambient_prompt


@pytest.mark.asyncio
async def test_primary_condition_appended_for_returning_patients(monkeypatch):
    client = _FakeLLMClient(_multi_field_json({"a": ["x"]}))
    monkeypatch.setattr(text_mod, "get_llm_client", lambda: client)

    await process_transcription(
        "t", [_make_field("a")], {}, is_ambient=True, primary_condition="asthma"
    )
    prompt = client.calls[0]["messages"][0]["content"]
    assert "returning patient" in prompt
    assert "asthma" in prompt


@pytest.mark.asyncio
async def test_transcript_is_user_message_and_model_from_config(monkeypatch):
    client = _FakeLLMClient(_multi_field_json({"a": []}))
    monkeypatch.setattr(text_mod, "get_llm_client", lambda: client)

    transcript = "The raw transcript text with patient details."
    await process_transcription(
        transcript, [_make_field("a")], {"name": "Doe, John", "gender": "F", "dob": "1990-01-01"}
    )

    call = client.calls[0]
    messages = call["messages"]
    assert messages[0]["role"] == "system"
    assert messages[1] == {"role": "user", "content": transcript}
    # Model comes from the encrypted config, not hardcoded.
    assert call["model"] == "test-model"
    # General options merged into the request plus a seed.
    assert call["options"]["num_ctx"] == GENERAL_OPTIONS["num_ctx"]
    assert "seed" in call["options"]
    # Patient context is folded into the system prompt.
    assert "Patient name: Doe, John" in messages[0]["content"]
    assert "Gender: F" in messages[0]["content"]
    assert "DOB: 1990-01-01" in messages[0]["content"]


@pytest.mark.asyncio
async def test_missing_field_key_yields_empty_string(monkeypatch):
    client = _FakeLLMClient(_multi_field_json({"a": ["x"]}))
    monkeypatch.setattr(text_mod, "get_llm_client", lambda: client)

    result = await process_transcription("t", [_make_field("a"), _make_field("missing")], {})
    assert result["fields"]["a"] == "• X"
    assert result["fields"]["missing"] == ""


@pytest.mark.asyncio
async def test_retries_once_then_raises(monkeypatch):
    call_state = {"n": 0}

    async def flaky_chat(**kwargs):  # noqa: ARG001 - real client.chat signature
        call_state["n"] += 1
        if call_state["n"] == 1:
            raise ValueError("first attempt fails")
        return {"message": {"content": _multi_field_json({"a": ["ok"]})}}

    class _FlakyClient:
        def __init__(self):
            self.chat = flaky_chat
            self.calls = []

    client = _FlakyClient()
    monkeypatch.setattr(text_mod, "get_llm_client", lambda: client)

    result = await process_transcription("t", [_make_field("a")], {})
    assert result["fields"]["a"] == "• Ok"
    assert call_state["n"] == 2  # one retry


@pytest.mark.asyncio
async def test_exhausted_retries_raise(monkeypatch):
    client = _FakeLLMClient(exc=RuntimeError("always fails"))
    monkeypatch.setattr(text_mod, "get_llm_client", lambda: client)

    with pytest.raises(RuntimeError):
        await process_transcription("t", [_make_field("a")], {})
    # 1 initial + 1 retry = 2 total calls.
    assert len(client.calls) == 2


@pytest.mark.asyncio
async def test_processing_errors_propagate_to_the_api_layer(monkeypatch):
    """The API relies on the exception propagating to flag processingError
    (the raw-transcript-preserved-on-failure contract)."""
    client = _FakeLLMClient(exc=RuntimeError("boom"))
    monkeypatch.setattr(text_mod, "get_llm_client", lambda: client)

    with pytest.raises(RuntimeError, match="boom"):
        await process_transcription("t", [_make_field("a")], {})


# ---------------------------------------------------------------------------
# text.py — pure helpers
# ---------------------------------------------------------------------------


def test_build_patient_context_includes_only_provided_keys():
    assert _build_patient_context({}) == ""
    ctx = _build_patient_context(
        {"name": "Doe, John", "gender": "M", "dob": "1990-01-01", "age": "54"}
    )
    assert "Patient name: Doe, John" in ctx
    assert "Age: 54" in ctx
    assert "Gender: M" in ctx
    assert "DOB: 1990-01-01" in ctx


def test_build_patient_context_skips_none_values():
    ctx = _build_patient_context({"name": "Doe, John", "gender": None, "dob": None})
    assert "Patient name: Doe, John" in ctx
    assert "Gender" not in ctx
    assert "DOB" not in ctx


def test_capitalize_first_char():
    assert _capitalize_first_char("") == ""
    assert _capitalize_first_char("hello") == "Hello"
    assert _capitalize_first_char("Persian") == "Persian"


# ---------------------------------------------------------------------------
# Invariant #5 — this path has no PHI egress beyond the LLM client
# ---------------------------------------------------------------------------


def test_text_module_has_no_external_egress_imports():
    """process_transcription must not pull in any non-LLM egress client.

    If a future change adds a PubMed / Wikipedia / MCP / raw-HTTP import to
    this module, the ambient-note transcript (PHI) could be sent to an
    external service. Pin the import surface to catch that.
    """
    source = inspect.getsource(text_mod)
    forbidden = ("pubmed", "wikipedia", "aiohttp", "httpx", "requests.", "urllib")
    lowered = source.lower()
    for token in forbidden:
        assert token not in lowered, f"text.py must not reference '{token}'"


# ---------------------------------------------------------------------------
# transcribe.py — endpoint contracts (TestClient, everything mocked)
# ---------------------------------------------------------------------------


def _build_client() -> TestClient:
    app = FastAPI()
    app.include_router(transcribe_mod.router, prefix="/api/transcribe")
    return TestClient(app)


AUDIO_RESULT = {"text": "chief complaint is chest pain", "transcriptionDuration": 1.5}


def _audio_files(**overrides):
    data = {"file": ("a.wav", b"RIFFdummy-bytes", "audio/wav")}
    data.update(overrides)
    return data


def test_audio_success_contract(monkeypatch):
    process = AsyncMock(
        return_value={"fields": {"symptoms": "• Chest pain"}, "process_duration": 0.5}
    )
    monkeypatch.setattr(transcribe_mod, "transcribe_audio", AsyncMock(return_value=AUDIO_RESULT))
    monkeypatch.setattr(transcribe_mod, "process_transcription", process)

    resp = _build_client().post("/api/transcribe/audio", files=_audio_files())
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["fields"] == {"symptoms": "• Chest pain"}
    assert body["rawTranscription"] == AUDIO_RESULT["text"]
    assert body["transcriptionDuration"] == 1.5
    assert body["processDuration"] == 0.5
    assert body.get("processingError") is None
    # Delegates to the domain layer (invariant #2) with ambient on by default.
    process.assert_awaited_once()
    _, kwargs = process.call_args
    assert kwargs["transcript_text"] == AUDIO_RESULT["text"]
    assert kwargs["is_ambient"] is True


def test_audio_processing_failure_preserves_raw_transcript(monkeypatch):
    """If the LLM step fails after a successful ASR, the raw transcript is
    returned flagged (processingError) instead of a 500 — the paid-for ASR
    result must not be lost."""
    long_error = "LLM provider error: " + ("x" * 400)
    monkeypatch.setattr(transcribe_mod, "transcribe_audio", AsyncMock(return_value=AUDIO_RESULT))
    monkeypatch.setattr(
        transcribe_mod, "process_transcription", AsyncMock(side_effect=RuntimeError(long_error))
    )

    resp = _build_client().post("/api/transcribe/audio", files=_audio_files())
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["fields"] == {}
    # Raw transcript preserved.
    assert body["rawTranscription"] == AUDIO_RESULT["text"]
    assert body["transcriptionDuration"] == 1.5
    assert body["processDuration"] == 0.0
    # Error flagged, truncated to 300 chars.
    assert body["processingError"] is not None
    assert len(body["processingError"]) <= 300
    assert body["processingError"].startswith("LLM provider error:")


def test_audio_asr_failure_returns_500(monkeypatch):
    """A failure in the ASR step itself (no transcript produced) is a 500."""
    monkeypatch.setattr(
        transcribe_mod, "transcribe_audio", AsyncMock(side_effect=RuntimeError("asr down"))
    )
    resp = _build_client().post("/api/transcribe/audio", files=_audio_files())
    assert resp.status_code == 500


def test_audio_upload_cap_enforced(monkeypatch):
    """Uploads over MAX_AUDIO_UPLOAD_BYTES are rejected, not read into RAM."""
    monkeypatch.setattr(transcribe_mod, "MAX_AUDIO_UPLOAD_BYTES", 10)
    monkeypatch.setattr(transcribe_mod, "transcribe_audio", AsyncMock(return_value=AUDIO_RESULT))
    monkeypatch.setattr(
        transcribe_mod,
        "process_transcription",
        AsyncMock(return_value={"fields": {}, "process_duration": 0.0}),
    )

    # 20 bytes > 10-byte cap.
    resp = _build_client().post(
        "/api/transcribe/audio",
        files=_audio_files(file=("a.wav", b"0123456789ABCDEF", "audio/wav")),
    )
    # Characterized: the 413 from read_upload_limited is re-wrapped as a 500
    # by the endpoint's blanket except handler.
    assert resp.status_code == 500, resp.text
    assert "Internal server error" in resp.json()["detail"]


def test_audio_wires_template_and_patient_context(monkeypatch):
    process = AsyncMock(return_value={"fields": {}, "process_duration": 0.1})
    get_fields = lambda _key: [_make_field("symptoms")]  # noqa: E731
    get_patient = lambda _pid: {"primary_condition": "asthma"}  # noqa: E731
    monkeypatch.setattr(transcribe_mod, "transcribe_audio", AsyncMock(return_value=AUDIO_RESULT))
    monkeypatch.setattr(transcribe_mod, "process_transcription", process)
    monkeypatch.setattr("server.database.repositories.templates.get_template_fields", get_fields)
    monkeypatch.setattr("server.database.repositories.encounter.get_patient_by_id", get_patient)

    resp = _build_client().post(
        "/api/transcribe/audio",
        data={
            "name": "Doe, John",
            "gender": "F",
            "dob": "1990-01-01",
            "templateKey": "soap",
            "noteId": 7,
        },
        files={"file": ("a.wav", b"RIFFdummy-bytes", "audio/wav")},
    )
    assert resp.status_code == 200, resp.text

    _, kwargs = process.call_args
    assert kwargs["template_fields"] == [_make_field("symptoms")]
    assert kwargs["primary_condition"] == "asthma"
    # Name is normalized from "Last, First" to "First Last" for display.
    assert kwargs["patient_context"]["name"] == "John Doe"
    assert kwargs["patient_context"]["gender"] == "F"
    assert kwargs["patient_context"]["dob"] == "1990-01-01"


def test_audio_without_template_key_uses_no_fields(monkeypatch):
    process = AsyncMock(return_value={"fields": {}, "process_duration": 0.1})
    monkeypatch.setattr(transcribe_mod, "transcribe_audio", AsyncMock(return_value=AUDIO_RESULT))
    monkeypatch.setattr(transcribe_mod, "process_transcription", process)

    resp = _build_client().post("/api/transcribe/audio", files=_audio_files())
    assert resp.status_code == 200, resp.text
    _, kwargs = process.call_args
    assert kwargs["template_fields"] == []
    assert kwargs["primary_condition"] is None


def test_reprocess_success_and_failure_preserve_transcript(monkeypatch):
    monkeypatch.setattr(
        transcribe_mod,
        "process_transcription",
        AsyncMock(return_value={"fields": {"a": "• B"}, "process_duration": 0.2}),
    )
    client = _build_client()

    resp = client.post(
        "/api/transcribe/reprocess",
        data={"transcript_text": "my saved transcript", "original_transcription_duration": 3.0},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["fields"] == {"a": "• B"}
    assert body["rawTranscription"] == "my saved transcript"
    assert body["transcriptionDuration"] == 3.0

    # On processing failure the already-provided transcript is preserved.
    monkeypatch.setattr(
        transcribe_mod, "process_transcription", AsyncMock(side_effect=RuntimeError("nope"))
    )
    resp = client.post(
        "/api/transcribe/reprocess",
        data={"transcript_text": "my saved transcript"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["fields"] == {}
    assert body["rawTranscription"] == "my saved transcript"
    assert body["processingError"] is not None


def test_dictate_returns_transcript_and_duration(monkeypatch):
    monkeypatch.setattr(transcribe_mod, "transcribe_audio", AsyncMock(return_value=AUDIO_RESULT))
    resp = _build_client().post(
        "/api/transcribe/dictate", files={"file": ("d.wav", b"RIFF", "audio/wav")}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["transcription"] == AUDIO_RESULT["text"]
    assert body["transcriptionDuration"] == 1.5


def test_dictate_asr_failure_returns_500(monkeypatch):
    monkeypatch.setattr(
        transcribe_mod, "transcribe_audio", AsyncMock(side_effect=RuntimeError("asr down"))
    )
    resp = _build_client().post(
        "/api/transcribe/dictate", files={"file": ("d.wav", b"RIFF", "audio/wav")}
    )
    assert resp.status_code == 500


def test_process_document_from_text_requires_text():
    resp = _build_client().post(
        "/api/transcribe/process-document-from-text",
        json={"extracted_text": "   ", "templateKey": "soap"},
    )
    assert resp.status_code == 400


def test_process_document_from_text_failure_preserves_extracted_text(monkeypatch):
    monkeypatch.setattr(
        transcribe_mod,
        "process_document_text_with_template",
        AsyncMock(side_effect=RuntimeError("llm down")),
    )
    monkeypatch.setattr(
        "server.database.repositories.templates.get_template_fields",
        lambda _key: [_make_field("symptoms")],
    )

    resp = _build_client().post(
        "/api/transcribe/process-document-from-text",
        json={"extracted_text": "referral letter body", "templateKey": "soap"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["fields"] == {}
    assert body["rawTranscription"] == "referral letter body"
    assert body["processingError"] is not None
