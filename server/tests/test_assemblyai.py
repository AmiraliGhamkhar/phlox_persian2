"""Tests for the AssemblyAI provider: catalog, URL/model helpers, and the
pre-recorded REST file-transcription path.

Reference: https://www.assemblyai.com/docs/llms.txt (offline snapshot bundled
with the integration). AssemblyAI auth is the raw API key with no ``Bearer``
prefix, and pre-recorded jobs use the *plural* ``speech_models`` fallback list.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from server.transcription import assemblyai as aai
from server.transcription.audio import _transcribe_assemblyai
from server.utils.providers import (
    ASR_PROVIDERS,
    apply_asr_provider_defaults,
    resolve_asr_connection,
)


def test_assemblyai_catalog_entry():
    info = ASR_PROVIDERS["assemblyai"]
    assert info["protocol"] == "assemblyai"
    assert info["requires_api_key"] is True
    assert info["supports_live"] is True
    # Batch first, Persian-capable fallback second.
    assert info["default_models"] == ["universal-3-5-pro", "universal-2"]


def test_assemblyai_resolves_like_a_cloud_provider():
    connection = resolve_asr_connection(
        {"ASR_PROVIDER": "assemblyai", "ASR_KEY": "k", "ASR_MODEL": "universal-2"}
    )
    assert connection["protocol"] == "assemblyai"
    assert connection["supports_live"] is True
    assert connection["base_url"] == "https://api.assemblyai.com"


def test_apply_asr_provider_defaults_for_assemblyai():
    defaults = apply_asr_provider_defaults("assemblyai")
    assert defaults["ASR_PROVIDER"] == "assemblyai"
    assert defaults["ASR_BASE_URL"] == "https://api.assemblyai.com"
    assert defaults["ASR_MODEL"] == "universal-3-5-pro"


def test_assemblyai_url_helpers():
    assert aai.assemblyai_rest_url({}) == aai.ASSEMBLYAI_DEFAULT_URL
    assert aai.assemblyai_api_key({}) == ""
    assert aai.assemblyai_api_key({"ASR_KEY": " sm-raw "}) == "sm-raw"
    # Regional REST host pins the realtime endpoint to the same region.
    assert aai.assemblyai_streaming_url({}) == aai.ASSEMBLYAI_STREAMING_URL
    assert (
        aai.assemblyai_streaming_url({"ASR_BASE_URL": "https://api.eu.assemblyai.com"})
        == aai.ASSEMBLYAI_EU_STREAMING_URL
    )
    assert (
        aai.assemblyai_streaming_url({"ASR_BASE_URL": "https://api.assemblyai.com"})
        == aai.ASSEMBLYAI_STREAMING_URL
    )
    # A crafted host whose suffix merely contains "assemblyai.com" must not
    # select a regional endpoint (the registrable domain has to match exactly).
    assert (
        aai.assemblyai_streaming_url({"ASR_BASE_URL": "https://eu.evil.example.com"})
        == aai.ASSEMBLYAI_STREAMING_URL
    )
    assert (
        aai.assemblyai_streaming_url({"ASR_BASE_URL": "https://api.assemblyai.com.evil.com"})
        == aai.ASSEMBLYAI_STREAMING_URL
    )


def test_assemblyai_speech_model_mapping():
    # Pre-recorded uses the plural fallback list.
    assert aai.assemblyai_batch_speech_models("universal-3-5-pro") == [
        "universal-3-5-pro",
        "universal-2",
    ]
    assert aai.assemblyai_batch_speech_models("universal-2") == ["universal-2"]
    assert aai.assemblyai_batch_speech_models("") == ["universal-3-5-pro", "universal-2"]
    # Realtime uses a singular string; unknown values resolve to the default.
    assert aai.assemblyai_live_model("universal-2") == "universal-2"
    assert aai.assemblyai_live_model("universal-3-5-pro") == "universal-3-5-pro"
    assert aai.assemblyai_live_model("melia-1") == "universal-3-5-pro"


def _fake_response(status_code: int, json_body=None, text: str = ""):
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    response.text = text
    response.json.return_value = json_body or {}
    return response


def _mock_client(upload_resp, submit_resp, get_responses):
    """AsyncClient with ordered .post responses (upload, submit) then .get polls."""
    mock_client = AsyncMock()
    mock_client.post.side_effect = [upload_resp, submit_resp]
    mock_client.get.side_effect = get_responses
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


@pytest.mark.asyncio
async def test_transcribe_assemblyai_uploads_then_polls():
    config = {
        "ASR_PROVIDER": "assemblyai",
        "ASR_KEY": "raw-key",
        "ASR_MODEL": "universal-3-5-pro",
        "ASR_LANGUAGE": "auto",
    }
    responses = [
        _fake_response(200, {"upload_url": "https://cdn.assemblyai.com/upload/u1"}),
        _fake_response(200, {"id": "t-1", "status": "queued"}),
        _fake_response(200, {"id": "t-1", "status": "processing"}),
        _fake_response(
            200,
            {
                "id": "t-1",
                "status": "completed",
                "text": "سلام این یک آزمایش است.",
                "audio_duration": 8.0,
            },
        ),
    ]
    mock_client = _mock_client(responses[0], responses[1], responses[2:])

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await _transcribe_assemblyai(b"RIFF....WAVEdata", config)

    assert result["text"] == "سلام این یک آزمایش است."
    assert result["transcriptionDuration"] == 8.0

    # Auth is the raw key — no Bearer prefix (AssemblyAI's documented header).
    upload_call = mock_client.post.call_args_list[0]
    assert upload_call.kwargs["headers"]["Authorization"] == "raw-key"
    assert upload_call.args[0] == f"{aai.ASSEMBLYAI_DEFAULT_URL}/v2/upload"
    assert upload_call.kwargs["content"] == b"RIFF....WAVEdata"

    submit_call = mock_client.post.call_args_list[1]
    assert submit_call.args[0] == f"{aai.ASSEMBLYAI_DEFAULT_URL}/v2/transcript"
    body = submit_call.kwargs["json"]
    # Plural speech_models fallback list; auto omits language_code.
    assert body["speech_models"] == ["universal-3-5-pro", "universal-2"]
    assert "language_code" not in body
    assert body["audio_url"] == "https://cdn.assemblyai.com/upload/u1"

    poll_urls = [call.args[0] for call in mock_client.get.call_args_list]
    assert f"{aai.ASSEMBLYAI_DEFAULT_URL}/v2/transcript/t-1" in poll_urls


@pytest.mark.asyncio
async def test_transcribe_assemblyai_explicit_language_and_key_required():
    config = {
        "ASR_PROVIDER": "assemblyai",
        "ASR_KEY": "raw-key",
        "ASR_MODEL": "universal-2",
        "ASR_LANGUAGE": "fa",
    }
    responses = [
        _fake_response(200, {"upload_url": "https://cdn.assemblyai.com/upload/u2"}),
        _fake_response(200, {"id": "t-2", "status": "queued"}),
        _fake_response(
            200, {"id": "t-2", "status": "completed", "text": "سلام", "audio_duration": 2.0}
        ),
    ]
    mock_client = _mock_client(responses[0], responses[1], responses[2:])

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await _transcribe_assemblyai(b"RIFF....WAVEdata", config)

    assert result["text"] == "سلام"
    submit_body = mock_client.post.call_args_list[1].kwargs["json"]
    assert submit_body["speech_models"] == ["universal-2"]
    assert submit_body["language_code"] == "fa"

    # Missing key must fail before any network call.
    with pytest.raises(ValueError, match="AssemblyAI API key"):
        await _transcribe_assemblyai(b"data", {"ASR_PROVIDER": "assemblyai"})


@pytest.mark.asyncio
async def test_transcribe_assemblyai_error_status_is_raised():
    config = {
        "ASR_PROVIDER": "assemblyai",
        "ASR_KEY": "raw-key",
        "ASR_LANGUAGE": "auto",
    }
    responses = [
        _fake_response(200, {"upload_url": "https://cdn.assemblyai.com/upload/u3"}),
        _fake_response(401, {"error": "invalid api key"}),
    ]
    mock_client = _mock_client(responses[0], responses[1], [])

    with (
        patch("httpx.AsyncClient", return_value=mock_client),
        pytest.raises(ValueError, match="[Aa]uthentication failed"),
    ):
        await _transcribe_assemblyai(b"data", config)
