"""
Tests for transcription and transcription processing utilities.
We use pytest-asyncio to run async tests and patch external requests.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

# Import the public functions from the transcription module
from server.transcription import (
    _detect_audio_format,
    normalize_persian_text,
    process_transcription,
    resolve_asr_language,
    transcribe_audio,
)


def test_persian_normalization_preserves_mixed_medical_text():
    assert normalize_persian_text("بيمار كبد چرب HbA1c 7.2٪") == "بیمار کبد چرب HbA1c 7.2٪"


def test_resolve_asr_language_defaults_to_mixed_auto():
    assert resolve_asr_language({}) == "auto"
    assert resolve_asr_language({"ASR_LANGUAGE": "fa"}) == "fa"
    assert resolve_asr_language({"ASR_LANGUAGE": "fa-en"}) == "auto"
    # Older installations use the WHISPER_LANGUAGE compatibility key.
    assert resolve_asr_language({"WHISPER_LANGUAGE": "en"}) == "en"


# A simple asynchronous test for transcribe_audio
@pytest.mark.asyncio
async def test_transcribe_audio():
    fake_config = {
        "WHISPER_BASE_URL": "http://fake-whisper/",
        "WHISPER_MODEL": "whisper-1",
        "WHISPER_KEY": "fake-key",
        "LLM_PROVIDER": "external",
    }

    from server.database.config.manager import config_manager

    with patch.object(config_manager, "get_config", return_value=fake_config):
        # Build a fake httpx.Response
        fake_response = MagicMock(spec=httpx.Response)
        fake_response.status_code = 200
        fake_response.json.return_value = {"text": "Transcribed text"}
        fake_response.text = '{"text": "Transcribed text"}'

        # Build a mock AsyncClient whose post returns the fake response
        mock_client = AsyncMock()
        mock_client.post.return_value = fake_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("server.transcription.audio._detect_audio_format") as mock_detect,
            patch("httpx.AsyncClient", return_value=mock_client),
        ):
            mock_detect.return_value = ("recording.mp3", "audio/mpeg")

            result = await transcribe_audio(b"fake audio data")

            mock_detect.assert_called_once_with(b"fake audio data")
            assert "text" in result
            assert result["text"] == "Transcribed text"
            assert "transcriptionDuration" in result
            request_data = mock_client.post.call_args.kwargs["data"]
            assert request_data["task"] == "transcribe"
            assert "language" not in request_data  # auto keeps mixed-language detection enabled


@pytest.mark.asyncio
async def test_transcribe_audio_uses_canonical_persian_asr_configuration():
    fake_config = {
        "ASR_BASE_URL": "http://fake-asr/v1",
        "ASR_MODEL": "multilingual-asr",
        "ASR_KEY": "fake-key",
        "ASR_LANGUAGE": "fa-IR",
        "LLM_PROVIDER": "external",
    }

    from server.database.config.manager import config_manager

    with patch.object(config_manager, "get_config", return_value=fake_config):
        fake_response = MagicMock(spec=httpx.Response)
        fake_response.status_code = 200
        fake_response.json.return_value = {"text": "بیمار HbA1c هفت دارد"}
        fake_response.text = '{"text": "بیمار HbA1c هفت دارد"}'

        mock_client = AsyncMock()
        mock_client.post.return_value = fake_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "server.transcription.audio._detect_audio_format",
                return_value=("recording.wav", "audio/wav"),
            ),
            patch("httpx.AsyncClient", return_value=mock_client),
        ):
            result = await transcribe_audio(b"fake audio data")

        assert result["text"] == "بیمار HbA1c هفت دارد"
        request_data = mock_client.post.call_args.kwargs["data"]
        assert request_data["model"] == "multilingual-asr"
        assert request_data["task"] == "transcribe"
        assert request_data["language"] == "fa"
        assert mock_client.post.call_args.args[0] == "http://fake-asr/v1/audio/transcriptions"


# Test process_transcription with no non-persistent fields.
@pytest.mark.asyncio
async def test_process_transcription_no_fields():
    transcript_text = "This is a test transcript."
    template_fields = []  # no fields to process
    patient_context = {"name": "Doe, John", "dob": "1990-01-01", "gender": "M"}
    # Mock the LLM call layer since even empty fields triggers config/LLM access
    with patch("server.transcription.text.process_all_fields_concurrently", return_value={}):
        result = await process_transcription(transcript_text, template_fields, patient_context)  # ty: ignore
    # Expect fields dict to be empty, and process_duration present
    assert "fields" in result
    assert result["fields"] == {}
    assert "process_duration" in result
    assert isinstance(result["process_duration"], float)


# Test for the audio format detection function
def test_detect_audio_format():
    # Test MP3 detection
    mp3_data = b"ID3dummy data"
    filename, content_type = _detect_audio_format(mp3_data)
    assert filename == "recording.mp3"
    assert content_type == "audio/mpeg"

    # Test WAV detection
    wav_data = b"RIFFdummy WAVEdata"
    filename, content_type = _detect_audio_format(wav_data)
    assert filename == "recording.wav"
    assert content_type == "audio/wav"

    # Test OGG detection
    ogg_data = b"OggSdummy data"
    filename, content_type = _detect_audio_format(ogg_data)
    assert filename == "recording.ogg"
    assert content_type == "audio/ogg"

    # Test M4A detection
    m4a_data = b"dummyftypdata"
    filename, content_type = _detect_audio_format(m4a_data)
    assert filename == "recording.m4a"
    assert content_type == "audio/mp4"

    # Test unrecognized format (should default to WAV)
    unknown_data = b"unknown format data"
    filename, content_type = _detect_audio_format(unknown_data)
    assert filename == "recording.wav"
    assert content_type == "audio/wav"


# Test for API error handling with detailed error messages
@pytest.mark.asyncio
async def test_transcribe_audio_api_error():
    fake_config = {
        "WHISPER_BASE_URL": "http://fake-whisper/",
        "WHISPER_MODEL": "whisper-1",
        "WHISPER_KEY": "fake-key",
        "LLM_PROVIDER": "external",
    }

    from server.database.config.manager import config_manager

    with patch.object(config_manager, "get_config", return_value=fake_config):
        # Build a fake httpx.Response with an error status
        fake_response = MagicMock(spec=httpx.Response)
        fake_response.status_code = 400
        fake_response.text = '{"error": "Invalid request parameters"}'

        mock_client = AsyncMock()
        mock_client.post.return_value = fake_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("server.transcription.audio._detect_audio_format") as mock_detect,
            patch("httpx.AsyncClient", return_value=mock_client),
        ):
            mock_detect.return_value = ("recording.wav", "audio/wav")

            with pytest.raises(ValueError) as excinfo:
                await transcribe_audio(b"fake audio data")

            assert "Invalid request parameters" in str(excinfo.value)
