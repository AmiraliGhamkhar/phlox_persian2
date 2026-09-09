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


@pytest.mark.asyncio
async def test_transcribe_audio_dispatches_fireworks():
    fake_config = {
        "ASR_PROVIDER": "fireworks",
        "ASR_MODEL": "whisper-v3-turbo",
        "ASR_KEY": "fw-key",
        "ASR_LANGUAGE": "fa",
    }
    from server.database.config.manager import config_manager

    with patch.object(config_manager, "get_config", return_value=fake_config):
        fake_response = MagicMock(spec=httpx.Response)
        fake_response.status_code = 200
        fake_response.json.return_value = {"text": "درد قفسه سینه"}
        fake_response.text = '{"text": "درد قفسه سینه"}'

        mock_client = AsyncMock()
        mock_client.post.return_value = fake_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await transcribe_audio(b"RIFF....WAVEdata")

        assert result["text"] == "درد قفسه سینه"
        assert "audio-turbo" in mock_client.post.call_args.args[0]
        assert mock_client.post.call_args.kwargs["headers"]["Authorization"] == "Bearer fw-key"
        assert mock_client.post.call_args.kwargs["data"]["language"] == "fa"


@pytest.mark.asyncio
async def test_transcribe_audio_dispatches_shenava():
    fake_config = {
        "ASR_PROVIDER": "local",
        "ASR_MODEL": "shenava-koochik-v1.0-int4",
        "ASR_LANGUAGE": "fa",
        "LLM_PROVIDER": "local",
    }
    from server.database.config.manager import config_manager

    with (
        patch.object(config_manager, "get_config", return_value=fake_config),
        patch(
            "server.transcription.audio._transcribe_local_shenava",
            new_callable=AsyncMock,
            return_value={"text": "سلام", "transcriptionDuration": 0.1},
        ) as mock_shenava,
    ):
        result = await transcribe_audio(b"RIFF....WAVEdata")
        mock_shenava.assert_called_once()
        assert result["text"] == "سلام"


@pytest.mark.asyncio
async def test_transcribe_audio_dispatches_parakeet():
    fake_config = {
        "ASR_PROVIDER": "local",
        "ASR_MODEL": "parakeet-tdt-0.6b-v3-int8",
        "ASR_LANGUAGE": "en",
        "LLM_PROVIDER": "local",
    }
    from server.database.config.manager import config_manager

    with (
        patch.object(config_manager, "get_config", return_value=fake_config),
        patch(
            "server.transcription.audio._transcribe_local_parakeet",
            new_callable=AsyncMock,
            return_value={"text": "hello", "transcriptionDuration": 0.1},
        ) as mock_parakeet,
    ):
        result = await transcribe_audio(b"RIFF....WAVEdata")
        mock_parakeet.assert_called_once()
        assert result["text"] == "hello"


def test_dictate_returns_400_for_missing_provider_key():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from server.api.transcribe import router

    app = FastAPI()
    app.include_router(router, prefix="/api/transcribe")
    client = TestClient(app)

    with patch(
        "server.api.transcribe.transcribe_audio",
        new_callable=AsyncMock,
        side_effect=ValueError("A Fireworks API key is required for the selected ASR provider"),
    ):
        response = client.post(
            "/api/transcribe/dictate",
            files={"file": ("recording.wav", b"RIFF....WAVEdata", "audio/wav")},
        )
    assert response.status_code == 400
    assert "Fireworks API key" in response.json()["detail"]


def test_dictate_returns_asr_hygiene_metadata():
    """W1.5: /dictate surfaces flags/segments/vad so the UI can amber-flag
    weak spans and the report prompt can be told which spans are uncertain.
    Providers without per-segment stats degrade to empty structures."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from server.api.transcribe import router

    app = FastAPI()
    app.include_router(router, prefix="/api/transcribe")
    client = TestClient(app)

    with patch(
        "server.api.transcribe.transcribe_audio",
        new_callable=AsyncMock,
        return_value={
            "text": "بیمار با تب مراجعه کرد",
            "transcriptionDuration": 1.25,
            "segments": [{"id": 0, "text": "بیمار با تب", "confidence": "ok"}],
            "flags": [{"segment": 1, "reason": "low_confidence", "text": "مراجعه کرد"}],
            "vad": {"vad_applied": True, "trimmed_ms": 800},
        },
    ):
        response = client.post(
            "/api/transcribe/dictate",
            files={"file": ("recording.wav", b"RIFF....WAVEdata", "audio/wav")},
        )
    assert response.status_code == 200
    data = response.json()
    assert data["transcription"] == "بیمار با تب مراجعه کرد"
    assert data["segments"] == [{"id": 0, "text": "بیمار با تب", "confidence": "ok"}]
    assert data["flags"] == [{"segment": 1, "reason": "low_confidence", "text": "مراجعه کرد"}]
    assert data["vad"] == {"vad_applied": True, "trimmed_ms": 800}

    with patch(
        "server.api.transcribe.transcribe_audio",
        new_callable=AsyncMock,
        return_value={"text": "hello", "transcriptionDuration": 0.1},
    ):
        response = client.post(
            "/api/transcribe/dictate",
            files={"file": ("recording.wav", b"RIFF....WAVEdata", "audio/wav")},
        )
    assert response.status_code == 200
    data = response.json()
    assert data["segments"] == []
    assert data["flags"] == []
    assert data["vad"] == {}


def test_live_session_factory_picks_native_streaming():
    from server.transcription.live import (
        FireworksLiveSession,
        RollingWindowLiveSession,
        SpeechmaticsLiveSession,
        create_live_session,
        live_is_authoritative,
        pcm_to_wav,
    )

    async def emit(_event):
        return None

    speechmatics = create_live_session({"ASR_PROVIDER": "speechmatics", "ASR_KEY": "k"}, emit)
    fireworks = create_live_session(
        {"ASR_PROVIDER": "fireworks", "ASR_MODEL": "fireworks-asr-v2", "ASR_KEY": "k"},
        emit,
    )
    rolling = create_live_session({"ASR_PROVIDER": "openai", "ASR_MODEL": "whisper-1"}, emit)
    assert isinstance(speechmatics, SpeechmaticsLiveSession)
    assert isinstance(fireworks, FireworksLiveSession)
    assert isinstance(rolling, RollingWindowLiveSession)
    assert live_is_authoritative({"ASR_PROVIDER": "speechmatics"}) is True
    assert live_is_authoritative({"ASR_PROVIDER": "openai"}) is False
    wav = pcm_to_wav(b"\x00\x00" * 16)
    assert wav.startswith(b"RIFF")
