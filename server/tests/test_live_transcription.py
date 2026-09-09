"""Regression tests for the live (streaming) ASR adapters.

These target the provider-protocol issues that silently broke or degraded live
transcription with online providers:

1. ``language=auto`` was sent to Speechmatics/Fireworks *streaming* engines,
   which only support automatic language identification in Batch mode.
2. Fireworks streaming sends ``segments`` deltas, which the adapter ignored.
3. The Speechmatics adapter only handled three of the documented server
   messages, so ``Error``/``Warning``/``Info``/``EndOfUtterance`` never reached
   the clinician — a dead session looked like a quiet one, and the client kept
   treating the partial live text as the whole transcript.

The fakes reuse the *real* ``speechmatics.rt`` protocol models
(``TranscriptionConfig``, ``TranscriptResult``, ``ServerMessageType``, ...) and
only replace the transport, so a mistyped config field fails here rather than
in production with ``invalid_config``.
"""

import asyncio
import json
import sys
import time
import types
from typing import Any

import pytest

from server.transcription import live as live_module
from server.transcription.language import streaming_asr_language
from server.transcription.live import (
    ROLLING_BUFFER_SECONDS,
    SAMPLE_RATE,
    SPEECHMATICS_DEFAULT_URL,
    AssemblyAILiveSession,
    FireworksLiveSession,
    RollingWindowLiveSession,
    SpeechmaticsLiveSession,
    create_live_session,
    live_is_authoritative,
    speechmatics_rt_url,
)
from server.transcription.speechmatics_protocol import (
    AUDIO_QUEUE_MAX_FRAMES,
    MAX_DELAY_MAX_SECONDS,
    MAX_DELAY_MIN_SECONDS,
    classify_close,
    classify_error,
    dominant_speaker,
    live_settings,
)


async def _async_noop(_event: dict) -> None:  # type: ignore[no-untyped-def]
    """Async no-op emitter for constructing live sessions."""
    return None


# --------------------------------------------------------------------------
# Fake Speechmatics Realtime SDK
# --------------------------------------------------------------------------


class _FakeAsyncClient:
    """Minimal stand-in for ``speechmatics.rt.AsyncClient``.

    ``transcribe`` mirrors the real client: it announces ``RecognitionStarted``,
    acknowledges every audio frame with ``AudioAdded``, and returns once the
    source is exhausted (the adapter's queue sentinel). ``stall=True`` keeps the
    engine from reading so backpressure can be exercised.
    """

    def __init__(
        self,
        *,
        stall: bool = False,
        fail_with: BaseException | None = None,
        fail_early: bool = False,
        registry: dict | None = None,
        **kwargs,
    ):
        self.kwargs = kwargs
        self.handlers: dict[str, list] = {}
        self.closed = False
        self.forced_flushes = 0
        self.last_flush_timestamp: Any = None
        self.stall = stall
        self.fail_with = fail_with
        self.fail_early = fail_early
        self.registry = registry
        self._seq_no = 0
        if registry is not None:
            registry["client"] = self
            registry["client_kwargs"] = kwargs

    @staticmethod
    def _event_key(event) -> str:
        # ServerMessageType is a str-Enum: key on the wire value, not repr().
        return str(getattr(event, "value", event))

    def on(self, event, callback=None):
        if callback is not None:
            self.handlers.setdefault(self._event_key(event), []).append(callback)
        return callback

    def emit(self, message: dict) -> None:
        """Deliver a server message exactly as the SDK's receive loop would."""
        for callback in self.handlers.get(self._event_key(message["message"]), []):
            callback(message)

    async def transcribe(self, source, **kwargs):
        registry = self.registry
        if registry is not None:
            registry["config"] = kwargs.get("transcription_config")
            registry["audio_format"] = kwargs.get("audio_format")
        if self.fail_with is not None and self.fail_early:
            # Handshake/StartRecognition rejected: RecognitionStarted never comes.
            raise self.fail_with
        self.emit({"message": "RecognitionStarted", "id": "sess-1"})
        if self.fail_with is not None:
            raise self.fail_with
        if self.stall:
            # Engine accepts the session but never reads audio again.
            await asyncio.sleep(3600)
            return
        while True:
            chunk = await source.read()
            if not chunk:
                break
            self._seq_no += 1
            self.emit({"message": "AudioAdded", "seq_no": self._seq_no})
        self.emit({"message": "EndOfTranscript"})

    async def force_end_of_utterance(self, *, timestamp: Any = None):
        self.forced_flushes += 1
        self.last_flush_timestamp = timestamp

    async def close(self):
        self.closed = True


def _install_fake_rt(
    monkeypatch, *, stall: bool = False, fail_with=None, fail_early: bool = False
) -> dict:
    """Install a fake ``speechmatics.rt`` module with the real protocol models."""
    import speechmatics.rt as real_rt

    registry: dict[str, Any] = {}

    class _Client(_FakeAsyncClient):
        """Real-class stand-in: the adapter subclasses the SDK client."""

        def __init__(self, **kwargs):
            super().__init__(
                stall=stall, fail_with=fail_with, fail_early=fail_early, registry=registry, **kwargs
            )

    fake_rt: Any = types.ModuleType("speechmatics.rt")
    fake_rt.AsyncClient = _Client
    fake_rt.AudioEncoding = real_rt.AudioEncoding
    fake_rt.AudioFormat = real_rt.AudioFormat
    fake_rt.ConnectionConfig = real_rt.ConnectionConfig
    fake_rt.ConversationConfig = real_rt.ConversationConfig
    fake_rt.Model = real_rt.Model
    fake_rt.ServerMessageType = real_rt.ServerMessageType
    fake_rt.SpeakerDiarizationConfig = real_rt.SpeakerDiarizationConfig
    fake_rt.TranscriptionConfig = real_rt.TranscriptionConfig
    fake_rt.TranscriptResult = real_rt.TranscriptResult
    monkeypatch.setitem(sys.modules, "speechmatics.rt", fake_rt)
    return registry


async def _pump(times: int = 10) -> None:
    """Let queued session events reach the emitter."""
    for _ in range(times):
        await asyncio.sleep(0)


async def _started_session(
    monkeypatch,
    config: dict | None = None,
    *,
    stall: bool = False,
    fail_with=None,
    fail_early: bool = False,
):
    """Start a Speechmatics session against the fake SDK and collect events."""
    registry = _install_fake_rt(
        monkeypatch, stall=stall, fail_with=fail_with, fail_early=fail_early
    )
    events: list[dict] = []

    async def emit(event: dict) -> None:
        events.append(event)

    session = SpeechmaticsLiveSession(
        config or {"ASR_PROVIDER": "speechmatics", "ASR_KEY": "k", "ASR_MODEL": "enhanced"},
        emit,
    )
    await asyncio.wait_for(session.start(), timeout=5)
    return session, events, registry


def _transcript_message(text: str, speaker: str | None = None, *, forced: bool = False) -> dict:
    results = [
        {
            "type": "word",
            "start_time": 0.0,
            "end_time": 0.5,
            "alternatives": [
                {"content": word, "confidence": 0.9, **({"speaker": speaker} if speaker else {})}
            ],
        }
        for word in text.split()
    ]
    message: dict[str, Any] = {
        "message": "AddTranscript",
        "metadata": {"start_time": 0.0, "end_time": 1.0, "transcript": text},
        "results": results,
    }
    if forced:
        message["forced"] = True
    return message


# --------------------------------------------------------------------------
# Dispatch / endpoint resolution
# --------------------------------------------------------------------------


def test_assemblyai_live_session_is_native_and_authoritative():
    """AssemblyAI is a native streaming provider wired into the live dispatcher."""
    config = {"ASR_PROVIDER": "assemblyai", "ASR_KEY": "sm", "ASR_MODEL": "universal-3-5-pro"}
    assert isinstance(create_live_session(config, _async_noop), AssemblyAILiveSession)
    assert live_is_authoritative(config) is True


def test_streaming_language_maps_auto_to_fa():
    """``auto`` is the persisted default but streaming engines need an ISO code."""
    assert streaming_asr_language({}) == "fa"
    assert streaming_asr_language({"ASR_LANGUAGE": "auto"}) == "fa"
    assert streaming_asr_language({"WHISPER_LANGUAGE": "auto"}) == "fa"
    assert streaming_asr_language({"ASR_LANGUAGE": "fa"}) == "fa"
    assert streaming_asr_language({"ASR_LANGUAGE": "en"}) == "en"


def test_speechmatics_endpoint_falls_back_to_global_default():
    """Never connect to the SDK's EU2-only default for self-service accounts."""
    assert speechmatics_rt_url({}) == SPEECHMATICS_DEFAULT_URL
    custom = "wss://us.rt.speechmatics.com/v2"
    assert speechmatics_rt_url({"ASR_BASE_URL": custom}) == custom
    assert speechmatics_rt_url({"WHISPER_BASE_URL": custom}) == custom
    # ASR_BASE_URL wins over the legacy alias.
    assert (
        speechmatics_rt_url(
            {"ASR_BASE_URL": custom, "WHISPER_BASE_URL": "wss://eu.rt.speechmatics.com/v2"}
        )
        == custom
    )


# --------------------------------------------------------------------------
# Session configuration
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_speechmatics_session_builds_config_not_auto(monkeypatch):
    """The live session must not carry language=auto into StartRecognition."""
    session, _events, registry = await _started_session(monkeypatch)

    assert registry["client_kwargs"]["url"] == SPEECHMATICS_DEFAULT_URL
    config = registry["config"]
    assert config.language == "fa"
    assert config.enable_partials is True
    assert config.model == "enhanced"
    assert registry["audio_format"].sample_rate == SAMPLE_RATE
    assert await session.stop() == ""


@pytest.mark.asyncio
async def test_speechmatics_english_session_uses_medical_domain(monkeypatch):
    """English + enhanced selects the Enhanced Medical domain for live ASR."""
    _session, _events, registry = await _started_session(
        monkeypatch,
        {
            "ASR_PROVIDER": "speechmatics",
            "ASR_KEY": "k",
            "ASR_MODEL": "enhanced",
            "ASR_LANGUAGE": "en",
        },
    )

    config = registry["config"]
    assert config.language == "en"
    assert config.model == "enhanced"
    assert config.domain == "medical"


@pytest.mark.asyncio
async def test_speechmatics_persian_session_has_no_medical_domain(monkeypatch):
    """Persian has no Enhanced Medical variant; domain must stay None."""
    _session, _events, registry = await _started_session(
        monkeypatch,
        {
            "ASR_PROVIDER": "speechmatics",
            "ASR_KEY": "k",
            "ASR_MODEL": "enhanced",
            "ASR_LANGUAGE": "fa",
        },
    )

    config = registry["config"]
    assert config.language == "fa"
    assert getattr(config, "domain", None) is None


@pytest.mark.asyncio
async def test_speechmatics_live_rejects_melia1_batch_only(monkeypatch):
    """Melia 1 is not in the Realtime SDK Model enum; live must fail clearly."""
    _install_fake_rt(monkeypatch)

    async def emit(_event):
        return None

    session = SpeechmaticsLiveSession(
        {"ASR_PROVIDER": "speechmatics", "ASR_KEY": "k", "ASR_MODEL": "melia-1"},
        emit,
    )
    with pytest.raises(ValueError, match="Batch-only"):
        await session.start()


@pytest.mark.asyncio
async def test_speechmatics_turn_detection_enabled_by_default(monkeypatch):
    """conversation_config drives EndOfUtterance; it is on unless disabled."""
    _session, _events, registry = await _started_session(monkeypatch)
    config = registry["config"]
    assert config.conversation_config is not None
    assert config.conversation_config.end_of_utterance_silence_trigger > 0


@pytest.mark.asyncio
async def test_speechmatics_optional_features_stay_off_by_default(monkeypatch):
    """Optional config blocks are only sent when asked for (invalid_config risk)."""
    _session, _events, registry = await _started_session(monkeypatch)
    config = registry["config"]
    assert config.transcript_filtering_config is None
    assert config.punctuation_overrides is None
    assert config.diarization is None
    assert config.speaker_diarization_config is None


@pytest.mark.asyncio
async def test_speechmatics_optional_features_are_applied(monkeypatch):
    """Disfluency removal, punctuation and diarization reach StartRecognition."""
    _session, _events, registry = await _started_session(
        monkeypatch,
        {
            "ASR_PROVIDER": "speechmatics",
            "ASR_KEY": "k",
            "ASR_LIVE_REMOVE_DISFLUENCIES": "true",
            "ASR_LIVE_PUNCTUATION_SENSITIVITY": "0.8",
            "ASR_LIVE_DIARIZATION": "yes",
            "ASR_LIVE_MAX_SPEAKERS": "3",
            "ASR_LIVE_MAX_DELAY": "2.5",
        },
    )
    config = registry["config"]
    assert config.transcript_filtering_config == {"remove_disfluencies": True}
    assert config.punctuation_overrides == {"sensitivity": 0.8}
    assert config.diarization == "speaker"
    assert config.speaker_diarization_config.max_speakers == 3
    assert config.speaker_diarization_config.prefer_current_speaker is True
    assert config.max_delay == 2.5


def test_live_settings_clamp_to_documented_ranges():
    """Out-of-range tuning must never be forwarded to the service."""
    assert live_settings({"ASR_LIVE_MAX_DELAY": "99"}).max_delay == MAX_DELAY_MAX_SECONDS
    assert live_settings({"ASR_LIVE_MAX_DELAY": "0.01"}).max_delay == MAX_DELAY_MIN_SECONDS
    assert live_settings({"ASR_LIVE_MAX_DELAY": "nonsense"}).max_delay == 1.0
    # end_of_utterance_silence_trigger is documented as 0..2 (0 disables).
    assert live_settings({"ASR_LIVE_END_OF_UTTERANCE_TRIGGER": "12"}).end_of_utterance_trigger == 2
    assert live_settings({"ASR_LIVE_END_OF_UTTERANCE_TRIGGER": "0"}).turn_detection_enabled is False
    # max_speakers is documented as >= 2.
    assert live_settings({"ASR_LIVE_MAX_SPEAKERS": "1"}).max_speakers == 2
    assert live_settings({"ASR_LIVE_MAX_DELAY_MODE": "fixed"}).max_delay_mode == "fixed"
    assert live_settings({"ASR_LIVE_MAX_DELAY_MODE": "bogus"}).max_delay_mode == "flexible"


# --------------------------------------------------------------------------
# Connection hardening
# --------------------------------------------------------------------------


def test_speechmatics_client_sets_keepalive_and_start_budget():
    """Ping keepalive plus an additional_vocab-sized start budget."""
    client = live_module._speechmatics_client(
        _FakeAsyncClient, api_key="k", url=SPEECHMATICS_DEFAULT_URL, start_timeout=30.0
    )
    conn_config = client.kwargs["conn_config"]
    assert conn_config.ping_interval == live_module.WS_PING_INTERVAL_SECONDS
    assert conn_config.ping_timeout == live_module.WS_PING_TIMEOUT_SECONDS
    assert conn_config.open_timeout == 30.0
    assert conn_config.max_size == live_module.WS_MAX_MESSAGE_BYTES


@pytest.mark.asyncio
async def test_speechmatics_client_start_wait_uses_the_wider_budget():
    """A large additional_vocab must not be cut off by the SDK's 5 s wait."""
    seen: list[float] = []

    class _SdkLike(_FakeAsyncClient):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self._recognition_started_evt = asyncio.Event()

        async def _wait_started_or_session_done(self, _evt, timeout):
            seen.append(timeout)

    client = live_module._speechmatics_client(_SdkLike, api_key="k", start_timeout=30.0)
    await client._wait_recognition_started()
    assert seen == [30.0]


@pytest.mark.asyncio
async def test_speechmatics_session_uses_the_vocabulary_start_budget(monkeypatch):
    """A biased session gets the longer start budget for RecognitionStarted."""
    registry = _install_fake_rt(monkeypatch)
    events: list[dict] = []

    async def emit(event: dict) -> None:
        events.append(event)

    session = SpeechmaticsLiveSession(
        {"ASR_PROVIDER": "speechmatics", "ASR_KEY": "k", "CLINICIAN_NAME": "دکتر رضایی"},
        emit,
    )
    await asyncio.wait_for(session.start(), timeout=5)
    # The bias vocabulary is built from the clinician identity + dictionary, so
    # the session must have been created with the vocabulary-sized budget.
    conn_config = registry["client"].kwargs["conn_config"]
    assert conn_config.open_timeout >= 30.0
    assert registry["config"].additional_vocab
    await session.stop()


# --------------------------------------------------------------------------
# Server-message handling (the documented in-band messages)
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_transcripts_are_emitted_in_order(monkeypatch):
    """Partials and finals are composed in arrival order."""
    session, events, registry = await _started_session(monkeypatch)
    client = registry["client"]

    client.emit(
        {
            "message": "AddPartialTranscript",
            "metadata": {"start_time": 0.0, "end_time": 0.5, "transcript": "بیمار"},
            "results": [],
        }
    )
    client.emit(_transcript_message("بیمار امروز"))
    await _pump()

    partials = [event for event in events if event["type"] == "partial"]
    finals = [event for event in events if event["type"] == "final"]
    assert partials[-1]["text"] == "بیمار"
    assert finals[-1]["text"] == "بیمار امروز"
    assert await session.stop() == "بیمار امروز"


@pytest.mark.asyncio
async def test_final_carries_dominant_speaker_when_diarizing(monkeypatch):
    """The diarization label travels with the final transcript segment."""
    _session, events, registry = await _started_session(monkeypatch)
    registry["client"].emit(
        {
            "message": "AddTranscript",
            "metadata": {"start_time": 0.0, "end_time": 2.0, "transcript": "سلام دکتر خوب"},
            "results": [
                {
                    "type": "word",
                    "start_time": 0.0,
                    "end_time": 0.5,
                    "alternatives": [{"content": "سلام", "confidence": 0.9, "speaker": "S1"}],
                },
                {
                    "type": "word",
                    "start_time": 0.5,
                    "end_time": 1.0,
                    "alternatives": [{"content": "دکتر", "confidence": 0.9, "speaker": "S2"}],
                },
                {
                    "type": "word",
                    "start_time": 1.0,
                    "end_time": 1.5,
                    "alternatives": [{"content": "خوب", "confidence": 0.9, "speaker": "S2"}],
                },
            ],
        }
    )
    await _pump()
    final = [event for event in events if event["type"] == "final"][-1]
    assert final["speaker"] == "S2"


@pytest.mark.asyncio
async def test_inband_error_fails_fast_and_downgrades_authority(monkeypatch):
    """quota_exceeded must surface, not look like silence."""
    session, events, registry = await _started_session(monkeypatch)

    registry["client"].emit(
        {
            "message": "Error",
            "type": "quota_exceeded",
            "reason": "Maximum concurrent connections reached",
            "code": 4005,
        }
    )
    await _pump()

    error = [event for event in events if event["type"] == "error"]
    assert len(error) == 1
    assert error[0]["error_type"] == "quota_exceeded"
    assert error[0]["fatal"] is True
    assert error[0]["retryable"] is True
    assert error[0]["authoritative"] is False
    assert "quota_exceeded" in error[0]["message"]
    assert session.failed is True

    # Fail fast: stop() must not wait out the drain timeout after a failure.
    started = time.monotonic()
    await session.stop()
    assert time.monotonic() - started < 5
    # Late audio is dropped rather than queued into a dead session.
    await session.feed_pcm(b"\x00" * 320)
    assert session._queue.qsize() == 0


@pytest.mark.asyncio
async def test_duration_limit_warning_downgrades_authority(monkeypatch):
    """The service ignores audio past the limit, so the live text is partial."""
    _session, events, registry = await _started_session(monkeypatch)

    registry["client"].emit(
        {
            "message": "Warning",
            "type": "duration_limit_exceeded",
            "reason": "Duration limit exceeded",
            "duration_limit": 7200,
        }
    )
    await _pump()

    warning = [event for event in events if event["type"] == "warning"][-1]
    assert warning["warning_type"] == "duration_limit_exceeded"
    assert warning["authoritative"] is False
    assert warning["message"]


@pytest.mark.asyncio
async def test_benign_warning_keeps_authority(monkeypatch):
    """A warning that does not end the session must not force a re-transcription."""
    _session, events, registry = await _started_session(monkeypatch)
    registry["client"].emit(
        {"message": "Warning", "type": "speaker_id", "reason": "No speaker identifiers found"}
    )
    await _pump()
    warning = [event for event in events if event["type"] == "warning"][-1]
    assert "authoritative" not in warning


@pytest.mark.asyncio
async def test_info_and_utterance_end_are_forwarded(monkeypatch):
    """Info (quality/quota) and EndOfUtterance reach the client."""
    _session, events, registry = await _started_session(monkeypatch)
    client = registry["client"]

    client.emit(
        {
            "message": "Info",
            "type": "concurrent_session_usage",
            "reason": "usage",
            "usage": 3,
            "quota": 5,
            "region": "eu",
            "last_updated": "2026-09-09T08:45:31Z",
        }
    )
    client.emit({"message": "EndOfUtterance", "metadata": {"start_time": 1.0, "end_time": 1.0}})
    await _pump()

    info = [event for event in events if event["type"] == "info"][-1]
    assert info["info_type"] == "concurrent_session_usage"
    assert (info["usage"], info["quota"], info["region"]) == (3, 5, "eu")

    utterance = [event for event in events if event["type"] == "utterance_end"][-1]
    assert utterance["forced"] is False
    assert utterance["end_time"] == 1.0


@pytest.mark.asyncio
async def test_end_of_transcript_emits_done(monkeypatch):
    """The client can settle on 'done' instead of waiting out its stop timeout."""
    session, events, _registry = await _started_session(monkeypatch)
    await session.stop()
    assert any(event["type"] == "done" for event in events)


@pytest.mark.asyncio
async def test_stop_forces_the_trailing_utterance(monkeypatch):
    """ForceEndOfUtterance flushes the last partial before EndOfStream."""
    session, _events, registry = await _started_session(monkeypatch)
    client = registry["client"]
    assert client.forced_flushes == 0
    await session.stop()
    assert client.forced_flushes == 1
    assert client.closed is True


@pytest.mark.asyncio
async def test_flush_finalizes_without_ending_the_session(monkeypatch):
    """The pause path flushes and keeps streaming."""
    session, _events, registry = await _started_session(monkeypatch)
    await session.flush()
    assert registry["client"].forced_flushes == 1
    assert registry["client"].closed is False
    await session.stop()


@pytest.mark.asyncio
async def test_transport_failure_is_classified_and_reported(monkeypatch):
    """A dropped connection surfaces as a typed fatal error, not silence."""
    import speechmatics.rt as real_rt

    session, events, _registry = await _started_session(
        monkeypatch, fail_with=real_rt.ConnectionError("WebSocket connection error")
    )
    await _pump()

    error = [event for event in events if event["type"] == "error"][-1]
    assert error["error_type"] == "transport_error"
    assert error["fatal"] is True
    assert error["authoritative"] is False
    assert "WebSocket connection error" in error["message"]
    assert session.failed is True
    assert await session.stop() == ""


@pytest.mark.asyncio
async def test_rejected_handshake_fails_loudly(monkeypatch):
    """A session rejected before RecognitionStarted must raise, not hang."""
    monkeypatch.setattr(live_module, "START_TIMEOUT_SECONDS", 0.2)
    monkeypatch.setattr(live_module, "START_TIMEOUT_WITH_VOCAB_SECONDS", 0.2)
    monkeypatch.setattr(live_module, "START_GRACE_SECONDS", 0.05)

    import speechmatics.rt as real_rt

    _install_fake_rt(monkeypatch, fail_with=real_rt.TimeoutError("no response"), fail_early=True)
    events: list[dict] = []

    async def emit(event: dict) -> None:
        events.append(event)

    session = SpeechmaticsLiveSession({"ASR_PROVIDER": "speechmatics", "ASR_KEY": "k"}, emit)
    with pytest.raises(ValueError, match="live session failed"):
        await asyncio.wait_for(session.start(), timeout=5)

    assert session.failed is True
    error = [event for event in events if event["type"] == "error"][-1]
    assert error["error_type"] == "transport_error"
    assert error["authoritative"] is False
    assert await session.stop() == ""


@pytest.mark.asyncio
async def test_repeated_failures_are_reported_once(monkeypatch):
    """The clinician gets one error, however many ways the session dies."""
    session, events, registry = await _started_session(monkeypatch)
    client = registry["client"]

    client.emit({"message": "Error", "type": "quota_exceeded", "reason": "full", "code": 4005})
    client.emit({"message": "Error", "type": "job_error", "reason": "later", "code": 4013})
    await _pump()

    errors = [event for event in events if event["type"] == "error"]
    assert len(errors) == 1
    assert errors[0]["error_type"] == "quota_exceeded"
    await session.stop()


# --------------------------------------------------------------------------
# Backpressure / resource hardening
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stalled_engine_fails_instead_of_buffering_forever(monkeypatch):
    """A full queue past the deadline is fatal, not a silent memory leak."""
    monkeypatch.setattr(live_module, "AUDIO_QUEUE_PUT_TIMEOUT_SECONDS", 0.05)
    session, events, _registry = await _started_session(monkeypatch, stall=True)

    for _ in range(AUDIO_QUEUE_MAX_FRAMES + 2):
        await session.feed_pcm(b"\x00" * 8192)
    await _pump()

    error = [event for event in events if event["type"] == "error"][-1]
    assert error["error_type"] == "audio_stalled"
    assert error["authoritative"] is False
    assert session._queue.qsize() <= AUDIO_QUEUE_MAX_FRAMES
    session._task.cancel()
    await session.stop()


@pytest.mark.asyncio
async def test_missing_audio_acknowledgement_is_detected(monkeypatch):
    """No AudioAdded while audio flows means the session is dead."""
    monkeypatch.setattr(live_module, "AUDIO_ACK_STALL_SECONDS", 1)
    session, events, _registry = await _started_session(monkeypatch, stall=True)
    session._last_ack = time.monotonic() - 60

    await session.feed_pcm(b"\x00" * 8192)
    await _pump()

    error = [event for event in events if event["type"] == "error"][-1]
    assert error["error_type"] == "audio_stalled"
    session._task.cancel()
    await session.stop()


@pytest.mark.asyncio
async def test_native_sessions_do_not_buffer_pcm(monkeypatch):
    """Streaming adapters forward audio; they must not keep a copy of it."""
    session, _events, registry = await _started_session(monkeypatch)
    for _ in range(20):
        await session.feed_pcm(b"\x00" * 8192)
    await _pump()
    assert not hasattr(session, "_pcm")
    # The frames were handed to the engine (AudioAdded came back for each).
    assert registry["client"]._seq_no == 20
    await session.stop()


@pytest.mark.asyncio
async def test_rolling_window_buffer_is_bounded(monkeypatch):
    """The fallback adapter keeps a capped window, not the whole recording."""
    captured: list[bytes] = []

    async def fake_transcribe(wav: bytes):
        captured.append(wav)
        return {"text": "متن", "transcriptionDuration": 0.01}

    import server.transcription.audio as audio_module

    monkeypatch.setattr(audio_module, "transcribe_audio", fake_transcribe)

    session = RollingWindowLiveSession({}, _async_noop)
    # Only the buffer cap is under test: keep the window transcriber idle.
    session._busy = True
    window_bytes = int(ROLLING_BUFFER_SECONDS * SAMPLE_RATE * 2)
    for _ in range(4000):  # ~32 s per 1000 frames at 16 kHz s16le
        await session.feed_pcm(b"\x00" * 3200)
    assert len(session._pcm) <= window_bytes


def test_rolling_window_cap_exceeds_the_transcribed_window():
    """The cap must stay larger than what the adapter actually transcribes."""
    assert ROLLING_BUFFER_SECONDS > live_module.ROLLING_WINDOW_SECONDS


# --------------------------------------------------------------------------
# Protocol classification helpers
# --------------------------------------------------------------------------


def test_error_classification_covers_documented_types():
    """Documented error types get a message; retry guidance matches the docs."""
    for error_type, retryable in [
        ("quota_exceeded", True),
        ("job_error", True),
        ("timelimit_exceeded", False),
        ("not_authorised", False),
        ("idle_timeout", False),
    ]:
        info = classify_error(error_type, "reason text", 4005)
        assert info.retryable is retryable
        assert info.error_type == error_type
        assert error_type in info.message
        assert "reason text" in info.message

    unknown = classify_error("something_new", "detail")
    assert unknown.error_type == "something_new"
    assert unknown.retryable is False


def test_bare_close_is_classified_from_the_documented_code_table():
    """A close with no in-band Error still tells the user what happened."""
    info = classify_close(1011, "internal_error")
    assert info.error_type == "internal_error"
    assert info.retryable is True
    assert info.close_code == 1011
    assert classify_close(None).error_type == "transport_error"


def test_dominant_speaker_picks_the_majority_label():
    class _Alt:
        def __init__(self, speaker):
            self.speaker = speaker

    class _Result:
        def __init__(self, speaker):
            self.alternatives = [_Alt(speaker)] if speaker is not None else None

    assert dominant_speaker([_Result("S1"), _Result("S2"), _Result("S2")]) == "S2"
    assert dominant_speaker([_Result(None), _Result(None)]) is None
    assert dominant_speaker("not a list") is None


# --------------------------------------------------------------------------
# Fireworks (unchanged behaviour, kept as a regression guard)
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fireworks_segments_are_parsed():
    """Fireworks streams `segments` deltas; the adapter must forward them."""
    events = []

    async def emit(event):
        events.append(event)

    session = FireworksLiveSession({"ASR_PROVIDER": "fireworks", "ASR_KEY": "k"}, emit)

    # delta with one pending and one finalized segment
    await session._handle_message(
        json.dumps(
            {
                "segments": [
                    {"id": 1, "text": "سلام", "is_final": True, "language": "fa"},
                    {"id": 2, "text": "دکتر", "is_final": False, "language": "fa"},
                ]
            }
        )
    )
    assert any(ev["type"] == "partial" for ev in events)
    assert "سلام" in events[-1]["text"]
    assert "دکتر" in events[-1]["text"]

    # finalized delta for the pending segment
    await session._handle_message(
        json.dumps(
            {
                "segments": [
                    {"id": 2, "text": "دکتر", "is_final": True, "language": "fa"},
                ]
            }
        )
    )
    assert events[-1]["type"] == "final"
    assert "سلام" in events[-1]["text"]
    assert "دکتر" in events[-1]["text"]

    # ordered by segment id even when deltas arrive out of order
    await session._handle_message(
        json.dumps(
            {
                "segments": [
                    {"id": 7, "text": "پایان", "is_final": True, "language": "fa"},
                    {"id": 3, "text": "قبل", "is_final": True, "language": "fa"},
                ]
            }
        )
    )
    assert events[-1]["text"] == "سلام دکتر قبل پایان"
