"""Live / real-time speech-to-text adapters.

Native streaming:
- Speechmatics Realtime with ``enable_partials``
- AssemblyAI Realtime (Universal-2 / Universal-3.5 Pro)
- Fireworks Audio Streaming WebSocket

Fallback for batch-only engines (Whisper.cpp, OpenAI Audio, Parakeet,
Shenava, custom OpenAI-compatible ASR): rolling WAV windows over the
in-progress PCM buffer.
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import json
import logging
import os
import time
import wave
from collections.abc import Awaitable, Callable
from typing import Any

from server.transcription.assemblyai import (
    assemblyai_api_key,
    assemblyai_live_model,
    assemblyai_model,
    assemblyai_streaming_url,
)
from server.transcription.language import (
    normalize_persian_text,
    speechmatics_medical_domain,
    streaming_asr_language,
)
from server.transcription.speechmatics_protocol import (
    AUDIO_ACK_STALL_SECONDS,
    AUDIO_QUEUE_MAX_FRAMES,
    AUDIO_QUEUE_PUT_TIMEOUT_SECONDS,
    DRAIN_TIMEOUT_SECONDS,
    FLUSH_TIMEOUT_SECONDS,
    PUNCTUATION_SENSITIVITY_DEFAULT,
    START_GRACE_SECONDS,
    START_TIMEOUT_SECONDS,
    START_TIMEOUT_WITH_VOCAB_SECONDS,
    ErrorInfo,
    LiveSettings,
    classify_error,
    dominant_speaker,
    live_settings,
    warning_message,
)
from server.utils.providers import ASR_PROVIDERS, resolve_asr_connection

logger = logging.getLogger(__name__)

EmitFn = Callable[[dict[str, Any]], Awaitable[None]]

SAMPLE_RATE = 16000
ROLLING_WINDOW_SECONDS = 5.0
ROLLING_HOP_SECONDS = 1.5
# The rolling-window adapter only ever re-transcribes the last few seconds, so
# the buffer it keeps is capped. A long ambient recording would otherwise
# buffer the whole session in memory (~115 MB/hour at 16 kHz s16le); the
# complete transcript for that path comes from the batch upload, not from here.
ROLLING_BUFFER_SECONDS = 120.0

# WebSocket keepalive for the realtime socket. Without pings a half-open TCP
# connection (dropped Wi-Fi, sleeping laptop) stays "connected" until the
# service's own one-hour idle timeout, and the clinician just sees a frozen
# transcript.
WS_PING_INTERVAL_SECONDS = 20.0
WS_PING_TIMEOUT_SECONDS = 20.0
WS_MAX_MESSAGE_BYTES = 4 * 1024 * 1024

# Speechmatics SaaS Realtime endpoints documented for production use. The
# global host auto-routes to the nearest region; ``eu.rt.speechmatics.com`` /
# ``us.rt.speechmatics.com`` pin a region. (The SDK's built-in EU2 default is
# not part of the documented production set and can fail the handshake.)
SPEECHMATICS_DEFAULT_URL = "wss://global.rt.speechmatics.com/v2"

# Warnings that mean the live text will not cover the whole recording, so the
# client must not treat it as authoritative and must still run the batch
# transcription of the full audio.
AUTHORITY_ENDING_WARNINGS = frozenset(
    {"duration_limit_exceeded", "idle_timeout", "session_timeout"}
)

# SDK exception classes mapped onto the documented error types, so a transport
# failure is reported with the same vocabulary as an in-band ``Error``.
_EXCEPTION_ERROR_TYPES = {
    "authenticationerror": "not_authorised",
    "configurationerror": "invalid_config",
    "connectionerror": "transport_error",
    "transporterror": "transport_error",
    "audioerror": "invalid_audio_type",
    "timeouterror": "transport_error",
}


def _exception_error_type(error: BaseException) -> str:
    """Map an SDK exception onto a documented realtime error type."""
    return _EXCEPTION_ERROR_TYPES.get(type(error).__name__.lower(), "unknown_error")


def _int_or_none(value: Any) -> int | None:
    """Coerce a message ``code`` field to int, tolerating junk."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _transcript_text(transcript_result: Any, message: dict) -> str:
    """Extract the segment transcript, falling back to the raw message."""
    try:
        return str(transcript_result.from_message(message).metadata.transcript or "")
    except (KeyError, TypeError, AttributeError, ValueError):
        metadata = message.get("metadata")
        if isinstance(metadata, dict):
            return str(metadata.get("transcript") or "")
        return ""


def _segment_speaker(transcript_result: Any, message: dict) -> str | None:
    """Dominant diarization label for a segment (only set when diarizing)."""
    try:
        results = transcript_result.from_message(message).results
    except (KeyError, TypeError, AttributeError, ValueError):
        return None
    return dominant_speaker(results)


def _speechmatics_connection_config(start_timeout: float) -> Any:
    """WebSocket tuning for the realtime socket, or ``None`` if unsupported."""
    try:
        from speechmatics.rt import ConnectionConfig

        return ConnectionConfig(
            open_timeout=start_timeout,
            ping_interval=WS_PING_INTERVAL_SECONDS,
            ping_timeout=WS_PING_TIMEOUT_SECONDS,
            max_size=WS_MAX_MESSAGE_BYTES,
        )
    except (ImportError, TypeError):  # pragma: no cover - older/other SDK
        return None


def _speechmatics_client(async_client_cls: Any, **kwargs: Any) -> Any:
    """Build a Realtime client whose start wait honours ``additional_vocab``.

    The service documents that a session using ``additional_vocab`` can take up
    to 15 seconds to reach ``RecognitionStarted``, but SDK 1.1.1 waits a fixed
    5 seconds (``_wait_recognition_started``), which makes a large bias
    vocabulary fail every live session. The subclass only widens that wait and
    falls back to the vendor behaviour if the SDK internals ever change.
    """
    start_timeout = float(kwargs.pop("start_timeout", START_TIMEOUT_SECONDS))

    class _StartBudgetClient(async_client_cls):  # type: ignore[misc,valid-type]
        async def _wait_recognition_started(self, timeout: float = 5.0) -> None:
            waiter = getattr(self, "_wait_started_or_session_done", None)
            started = getattr(self, "_recognition_started_evt", None)
            if waiter is None or started is None:  # pragma: no cover - SDK drift
                return await super()._wait_recognition_started(timeout)
            await waiter(started, max(timeout, start_timeout))

    conn_config = _speechmatics_connection_config(start_timeout)
    if conn_config is not None and "conn_config" not in kwargs:
        kwargs["conn_config"] = conn_config
    return _StartBudgetClient(**kwargs)


def speechmatics_rt_url(config: dict[str, Any]) -> str:
    """Resolve the Speechmatics Realtime endpoint for a session.

    Prefers the user-configured ``ASR_BASE_URL`` (regional pinning, custom
    runtime), falls back to the provider catalog, then to the documented
    global endpoint. Never returns an empty URL: the SDK's
    ``wss://eu2.rt.speechmatics.com/v2`` default is a legacy/enterprise-only
    host and silently fails for self-service accounts.
    """
    url = str(config.get("ASR_BASE_URL") or config.get("WHISPER_BASE_URL") or "").strip()
    if url:
        return url
    url = os.environ.get("SPEECHMATICS_RT_URL") or ""
    if url.strip():
        return url.strip()
    return str(
        (ASR_PROVIDERS.get("speechmatics") or {}).get("default_base_url")
        or SPEECHMATICS_DEFAULT_URL
    )


def pcm_to_wav(pcm: bytes, sample_rate: int = SAMPLE_RATE) -> bytes:
    """Wrap s16le mono PCM in a WAV container."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm)
    return buffer.getvalue()


class LiveSession:
    """Base class for a live transcription session."""

    async def start(self) -> None:
        return None

    async def feed_pcm(self, pcm: bytes) -> None:
        raise NotImplementedError

    async def flush(self) -> None:
        """Finalize any pending utterance without ending the session."""
        return None

    async def stop(self) -> str:
        return ""


class SpeechmaticsLiveSession(LiveSession):
    """Speechmatics Realtime with partial transcripts enabled.

    The adapter speaks the documented Realtime protocol end to end: it
    registers handlers for every server message the service can send
    (``Error``, ``Warning``, ``Info``, ``EndOfUtterance``, ``EndOfTranscript``,
    ``AudioAdded`` as well as the transcript messages), turns them into typed
    client frames, and fails fast — a dead realtime session must never look
    like a working one, because the caller uses that signal to decide whether
    the full recording still needs a batch transcription.
    """

    def __init__(self, config: dict[str, Any], emit: EmitFn):
        self.config = config
        self.emit = emit
        self.settings: LiveSettings = live_settings(config)
        self._finals: list[str] = []
        self._partial = ""
        self._client = None
        self._task: asyncio.Task | None = None
        self._pump_task: asyncio.Task | None = None
        # Bounded on purpose: the service documents that it may read audio
        # slower than the client sends it. An unbounded queue would turn that
        # backpressure into unbounded memory growth; a bounded one makes it
        # observable and, past a deadline, fatal (see feed_pcm).
        self._queue: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=AUDIO_QUEUE_MAX_FRAMES)
        # Transcript events arrive as SDK callbacks; they are routed through
        # this queue and processed by a single pump task so partials, finals
        # and errors are emitted in arrival order (unreferenced create_task
        # calls can be garbage-collected and reorder).
        self._events: asyncio.Queue = asyncio.Queue()
        self._started = asyncio.Event()
        self._failure: ErrorInfo | None = None
        self._stopping = False
        self._frames_sent = 0
        self._frames_acked = 0
        self._last_ack = 0.0

    @property
    def failed(self) -> bool:
        """Whether the realtime session terminated abnormally."""
        return self._failure is not None

    async def start(self) -> None:
        try:
            from speechmatics.rt import (
                AsyncClient,
                AudioEncoding,
                AudioFormat,
                ConversationConfig,
                Model,
                ServerMessageType,
                SpeakerDiarizationConfig,
                TranscriptionConfig,
                TranscriptResult,
            )
        except ImportError as error:
            raise ValueError(
                "Speechmatics support is not installed in this server build"
            ) from error

        api_key = str(self.config.get("ASR_KEY") or self.config.get("WHISPER_KEY") or "").strip()
        if not api_key:
            raise ValueError("A Speechmatics API key is required for live transcription")

        # Realtime has no automatic language identification: ``auto`` (the app
        # default, valid for Batch) must be mapped to an explicit code or the
        # session is rejected before any audio is accepted.
        speechmatics_language = streaming_asr_language(self.config)
        # Map the configured operating point onto the v1 ``Model`` enum; any
        # unrecognised value falls back to the default ``enhanced`` model.
        model_name = str(self.config.get("ASR_MODEL") or "enhanced").strip().lower()
        if model_name == "melia-1":
            raise ValueError(
                "Melia 1 is a Batch-only model and is not available for live "
                "transcription on the production Realtime endpoint (an early "
                "Realtime preview runs at wss://preview.rt.speechmatics.com/v2 "
                "with language 'multi'). Use 'enhanced' or 'standard' for live, "
                "or upload the recording and let the Batch path handle it."
            )
        model = Model.STANDARD if model_name == "standard" else Model.ENHANCED

        # Context biasing for live sessions too (plan ref A2): the clinic
        # lexicon and clinician identity. Fail-open — a vocabulary problem must
        # never kill the microphone path.
        additional_vocab = None
        try:
            from server.transcription.asr_context import (
                build_additional_vocab,
                build_bias_terms,
            )

            additional_vocab = build_additional_vocab(build_bias_terms(config=self.config))
        except Exception:  # pragma: no cover - defensive
            logger.debug("Live ASR bias vocabulary failed; continuing unbiased", exc_info=True)

        # additional_vocab is documented to add up to ~15 s before the session
        # starts, while the SDK waits only 5 s for RecognitionStarted. Size the
        # start budget to what we actually send.
        start_timeout = (
            START_TIMEOUT_WITH_VOCAB_SECONDS if additional_vocab else START_TIMEOUT_SECONDS
        )
        client = _speechmatics_client(
            AsyncClient,
            api_key=api_key,
            url=speechmatics_rt_url(self.config),
            start_timeout=start_timeout,
        )
        self._client = client
        self._last_ack = time.monotonic()

        # The SDK delivers callbacks synchronously from its own receive loop,
        # so they are queued and processed by one pump task (ordered emit, no
        # floating tasks).
        def _queue_event(kind: str) -> Callable[[dict], None]:
            def handler(message: dict) -> None:
                self._events.put_nowait((kind, message))

            return handler

        def on_started(_message: dict) -> None:
            self._started.set()

        async def _pump_events() -> None:
            while True:
                kind, message = await self._events.get()
                if message is None:
                    return
                if kind == "partial":
                    text = _transcript_text(TranscriptResult, message)
                    if text:
                        self._partial = text
                        await self._emit({"type": "partial", "text": _compose(self._finals, text)})
                elif kind == "final":
                    text = _transcript_text(TranscriptResult, message)
                    if text:
                        self._finals.append(text)
                        self._partial = ""
                        event: dict[str, Any] = {
                            "type": "final",
                            "text": _compose(self._finals, ""),
                        }
                        speaker = _segment_speaker(TranscriptResult, message)
                        if speaker:
                            event["speaker"] = speaker
                        if message.get("forced"):
                            event["forced"] = True
                        await self._emit(event)
                elif kind == "error":
                    await self._handle_error_message(message)
                    return
                elif kind == "warning":
                    await self._handle_warning(message)
                elif kind == "info":
                    await self._handle_info(message)
                elif kind == "utterance_end":
                    await self._handle_utterance_end(message)
                elif kind == "end_of_transcript":
                    await self._emit({"type": "done"})

        client.on(ServerMessageType.ADD_PARTIAL_TRANSCRIPT, _queue_event("partial"))
        client.on(ServerMessageType.ADD_TRANSCRIPT, _queue_event("final"))
        client.on(ServerMessageType.RECOGNITION_STARTED, on_started)
        # Without these the service's own diagnostics never leave the SDK log:
        # quota_exceeded, timelimit_exceeded, idle/session timeouts and the
        # duration-limit warning would surface only as silence.
        client.on(ServerMessageType.ERROR, _queue_event("error"))
        client.on(ServerMessageType.WARNING, _queue_event("warning"))
        client.on(ServerMessageType.INFO, _queue_event("info"))
        client.on(ServerMessageType.END_OF_UTTERANCE, _queue_event("utterance_end"))
        client.on(ServerMessageType.END_OF_TRANSCRIPT, _queue_event("end_of_transcript"))
        client.on(ServerMessageType.AUDIO_ADDED, self._note_audio_ack)

        async def _run() -> None:
            class _QueueAudio:
                def __init__(self, queue: asyncio.Queue[bytes | None]):
                    self.queue = queue

                async def read(self, _size: int = -1) -> bytes:
                    chunk = await self.queue.get()
                    if chunk is None:
                        return b""
                    return chunk

            try:
                transcription_kwargs: dict[str, Any] = {
                    "language": speechmatics_language,
                    "model": model,
                    "enable_partials": True,
                    "max_delay": self.settings.max_delay,
                    "max_delay_mode": self.settings.max_delay_mode,
                    "domain": speechmatics_medical_domain(model_name, speechmatics_language),
                }
                # Only send the knobs that differ from the documented defaults:
                # an unnecessary field is an unnecessary invalid_config risk.
                if self.settings.punctuation_sensitivity != PUNCTUATION_SENSITIVITY_DEFAULT:
                    transcription_kwargs["punctuation_overrides"] = {
                        "sensitivity": self.settings.punctuation_sensitivity
                    }
                if self.settings.remove_disfluencies:
                    transcription_kwargs["transcript_filtering_config"] = {
                        "remove_disfluencies": True
                    }
                if self.settings.turn_detection_enabled:
                    transcription_kwargs["conversation_config"] = ConversationConfig(
                        end_of_utterance_silence_trigger=self.settings.end_of_utterance_trigger
                    )
                if self.settings.diarization:
                    transcription_kwargs["diarization"] = "speaker"
                    transcription_kwargs["speaker_diarization_config"] = SpeakerDiarizationConfig(
                        max_speakers=self.settings.max_speakers,
                        prefer_current_speaker=True,
                    )
                if additional_vocab:
                    transcription_kwargs["additional_vocab"] = additional_vocab
                # The SDK types `source` as BinaryIO but accepts any object
                # with a (possibly async) read(); the queue reader is one.
                await client.transcribe(
                    _QueueAudio(self._queue),
                    transcription_config=TranscriptionConfig(**transcription_kwargs),
                    audio_format=AudioFormat(
                        encoding=AudioEncoding.PCM_S16LE,
                        sample_rate=SAMPLE_RATE,
                        chunk_size=4096,
                    ),
                    timeout=None,
                )
            except Exception as error:
                # Fail fast and say why: the caller falls back to batch
                # transcription of the full recording.
                logger.error("Speechmatics live session failed: %s", error)
                await self._fail(
                    classify_error(_exception_error_type(error), str(error)),
                )

        self._pump_task = asyncio.create_task(_pump_events())
        self._task = asyncio.create_task(_run())

        # Do not report the live socket as ready until Speechmatics itself has
        # accepted the session (RecognitionStarted). Otherwise the client sees
        # "ready" and silence when the key/endpoint/quota is wrong — the exact
        # failure mode reported with online ASR.
        started_wait = asyncio.create_task(self._started.wait())
        try:
            done, _ = await asyncio.wait(
                {started_wait, self._task},
                timeout=start_timeout + START_GRACE_SECONDS,
                return_when=asyncio.FIRST_COMPLETED,
            )
        finally:
            if not started_wait.done():
                started_wait.cancel()
        if self._started.is_set():
            return
        if self._failure is not None:
            raise ValueError(f"Speechmatics live session failed: {self._failure.message}")
        if self._task.done():
            failure = classify_error("unknown_error", "session ended before it started")
            await self._fail(failure)
            raise ValueError(f"Speechmatics live session failed: {failure.message}")
        raise ValueError(
            f"Speechmatics live session did not start within "
            f"{start_timeout + START_GRACE_SECONDS:.0f} seconds; "
            "check the API key, the region endpoint (ASR_BASE_URL), and account quotas"
        )

    def _note_audio_ack(self, message: dict) -> None:
        """Track AudioAdded acknowledgements (the service's flow control)."""
        self._last_ack = time.monotonic()
        self._frames_acked = int(message.get("seq_no") or 0)

    async def feed_pcm(self, pcm: bytes) -> None:
        if not pcm or self._failure is not None or self._stopping:
            return
        now = time.monotonic()
        if now - self._last_ack > AUDIO_ACK_STALL_SECONDS:
            await self._fail(
                classify_error(
                    "audio_stalled",
                    f"no AudioAdded acknowledgement for {int(now - self._last_ack)}s",
                )
            )
            return
        self._frames_sent += 1
        try:
            self._queue.put_nowait(pcm)
            return
        except asyncio.QueueFull:
            pass
        # The engine is behind. Wait for it to catch up, but not forever: a
        # queue that stays full means audio would be lost either way, and a
        # failed session lets the caller re-transcribe the full recording.
        try:
            await asyncio.wait_for(self._queue.put(pcm), timeout=AUDIO_QUEUE_PUT_TIMEOUT_SECONDS)
        except TimeoutError:
            await self._fail(
                classify_error(
                    "audio_stalled",
                    f"audio queue stayed full for {int(AUDIO_QUEUE_PUT_TIMEOUT_SECONDS)}s",
                )
            )

    async def flush(self) -> None:
        """Finalize the pending utterance without ending the session.

        Sent when the clinician pauses recording, so the transcript on screen
        is not left mid-sentence for the length of the pause.
        """
        await self._flush_utterance()

    async def _flush_utterance(self) -> None:
        if self._client is None or self._failure is not None or not self._started.is_set():
            return
        flush = getattr(self._client, "force_end_of_utterance", None)
        if flush is None:
            return
        try:
            await asyncio.wait_for(flush(), timeout=FLUSH_TIMEOUT_SECONDS)
        except Exception:
            # ForceEndOfUtterance is an optimization; EndOfStream still flushes.
            logger.debug("ForceEndOfUtterance failed; EndOfStream will flush", exc_info=True)

    async def _handle_error_message(self, message: dict) -> None:
        await self._fail(
            classify_error(
                str(message.get("type") or ""),
                str(message.get("reason") or ""),
                _int_or_none(message.get("code")),
            )
        )

    async def _handle_warning(self, message: dict) -> None:
        warning_type = str(message.get("type") or "")
        reason = str(message.get("reason") or "")
        logger.warning("Speechmatics live warning: %s (%s)", warning_type, reason)
        event: dict[str, Any] = {
            "type": "warning",
            "warning_type": warning_type,
            "message": warning_message(warning_type, reason),
        }
        # These warnings mean the session is ending early or is about to be
        # killed, so the live text will not cover the whole recording: the
        # caller must still run the batch transcription.
        if warning_type in AUTHORITY_ENDING_WARNINGS:
            event["authoritative"] = False
        await self._emit(event)

    async def _handle_info(self, message: dict) -> None:
        info_type = str(message.get("type") or "")
        event: dict[str, Any] = {"type": "info", "info_type": info_type}
        for key in ("quality", "usage", "quota", "region", "last_updated", "reason"):
            if message.get(key) is not None:
                event[key] = message[key]
        logger.info(
            "Speechmatics live info: %s (quality=%s usage=%s/%s region=%s)",
            info_type,
            message.get("quality"),
            message.get("usage"),
            message.get("quota"),
            message.get("region"),
        )
        await self._emit(event)

    async def _handle_utterance_end(self, message: dict) -> None:
        await self._emit(
            {
                "type": "utterance_end",
                "forced": bool(message.get("forced")),
                "end_time": (message.get("metadata") or {}).get("end_time"),
            }
        )

    async def _fail(self, info: ErrorInfo) -> None:
        """Record a fatal failure and tell the client exactly what happened."""
        if self._failure is not None:
            return
        self._failure = info
        logger.error(
            "Speechmatics live session failed: %s (type=%s code=%s)",
            info.message,
            info.error_type,
            info.code,
        )
        await self._emit(
            {
                "type": "error",
                "error_type": info.error_type,
                "code": info.code,
                "message": info.message,
                "fatal": True,
                "retryable": info.retryable,
                # The live text is no longer a complete transcript, so the
                # caller must fall back to batch transcription.
                "authoritative": False,
            }
        )

    async def _emit(self, event: dict[str, Any]) -> None:
        try:
            await self.emit(event)
        except Exception:
            # A broken client socket must not take the session down: the
            # transcript is still returned by stop().
            logger.debug("Live event emit failed", exc_info=True)

    async def stop(self) -> str:
        if self._stopping:
            return normalize_persian_text(_compose(self._finals, self._partial))
        self._stopping = True
        # Finalize the trailing utterance before EndOfStream so the last
        # partial becomes a final instead of being dropped.
        await self._flush_utterance()
        try:
            self._queue.put_nowait(None)
        except asyncio.QueueFull:
            # A stalled consumer would otherwise block here forever, inside the
            # request handler's finally block.
            with contextlib.suppress(asyncio.QueueEmpty):
                self._queue.get_nowait()
            with contextlib.suppress(asyncio.QueueFull):
                self._queue.put_nowait(None)
        if self._task and not self._task.done():
            drain_timeout = FLUSH_TIMEOUT_SECONDS if self._failure else DRAIN_TIMEOUT_SECONDS
            try:
                await asyncio.wait_for(self._task, timeout=drain_timeout)
            except TimeoutError:
                self._task.cancel()
            except asyncio.CancelledError:
                # Awaiting an already-cancelled task re-raises CancelledError.
                # Swallow only that case; a cancellation of *this* coroutine
                # (client disconnect, server shutdown) must keep propagating.
                if not self._task.cancelled():
                    raise
        if self._client is not None:
            close = getattr(self._client, "close", None)
            if close is not None:
                try:
                    await asyncio.wait_for(close(), timeout=FLUSH_TIMEOUT_SECONDS)
                except Exception:
                    logger.debug("Speechmatics live client close failed", exc_info=True)
        # Drain the transcript queue: stop() is called by the caller to flush
        # trailing finals, so let the pump deliver queued events before it
        # exits.
        if self._pump_task:
            self._events.put_nowait(("final", None))
            try:
                await asyncio.wait_for(self._pump_task, timeout=DRAIN_TIMEOUT_SECONDS)
            except TimeoutError:
                self._pump_task.cancel()
        return normalize_persian_text(_compose(self._finals, self._partial))


class AssemblyAILiveSession(LiveSession):
    """AssemblyAI Realtime streaming (Universal-2 / Universal-3.5 Pro).

    Config is carried entirely in the connect query string
    (``wss://streaming.assemblyai.com/v3/ws?sample_rate=16000&speech_model=…``);
    there is no ``configure`` JSON frame. Audio is streamed as raw s16le PCM
    and the server replies with ``message_type`` frames such as
    ``SessionBegins``, ``PartialTranscript`` and ``FinalTranscript``.

    Auth uses the **raw API key with no ``Bearer`` prefix** on the WebSocket
    upgrade, matching the REST header form.
    """

    def __init__(self, config: dict[str, Any], emit: EmitFn):
        self.config = config
        self.emit = emit
        # No PCM is buffered here: the audio is forwarded to the service as it
        # arrives, and keeping a copy would grow without bound over a session.
        self._finals: list[str] = []
        self._partial = ""
        self._ws = None
        self._receiver: asyncio.Task | None = None
        self._error: str | None = None

    async def start(self) -> None:
        try:
            import websockets
        except ImportError as error:
            raise ValueError(
                "AssemblyAI live transcription requires the websockets package"
            ) from error

        api_key = assemblyai_api_key(self.config)
        if not api_key:
            raise ValueError("An AssemblyAI API key is required for live transcription")

        model = assemblyai_live_model(assemblyai_model(self.config))
        url = assemblyai_streaming_url(self.config)
        params = [f"sample_rate={SAMPLE_RATE}", f"speech_model={model}"]
        # ``mode=balanced`` is the documented operating mode for the realtime
        # flagship; it only applies to Universal-3.5 Pro.
        if model == "universal-3-5-pro":
            params.append("mode=balanced")
        url = f"{url}?{'&'.join(params)}"

        headers = {"Authorization": api_key}  # raw key — no Bearer prefix.
        try:
            self._ws = await websockets.connect(
                url,
                additional_headers=headers,
                max_size=8 * 1024 * 1024,
            )
        except TypeError:
            # websockets <14 compatibility path (arg renamed in v14).
            self._ws = await websockets.connect(
                url,
                extra_headers=headers,
                max_size=8 * 1024 * 1024,
            )

        async def _receive() -> None:
            ws = self._ws
            assert ws is not None  # only reachable after start() assigned _ws above
            try:
                async for message in ws:
                    if isinstance(message, bytes):
                        continue
                    await self._handle_message(message)
            except Exception as error:  # noqa: BLE001 - surface as live error
                logger.debug("AssemblyAI live receive ended: %s", error)
                self._error = str(error)

        self._receiver = asyncio.create_task(_receive())

    async def _handle_message(self, message: str) -> None:
        try:
            payload = json.loads(message)
        except json.JSONDecodeError:
            return
        if not isinstance(payload, dict):
            return

        # Realtime frames carry a ``message_type``; tolerate a bare ``type``.
        message_type = str(payload.get("message_type") or payload.get("type") or "").lower()

        if message_type in ("partialtranscript", "transcript"):
            if payload.get("text"):
                self._partial = str(payload["text"]).strip()
                await self.emit({"type": "partial", "text": _compose(self._finals, self._partial)})
            return
        if message_type == "finaltranscript":
            text = str(payload.get("text") or "").strip()
            if text:
                self._finals.append(text)
                self._partial = ""
                await self.emit({"type": "final", "text": _compose(self._finals, "")})
            return

    async def feed_pcm(self, pcm: bytes) -> None:
        if self._ws is not None:
            await self._ws.send(pcm)

    async def stop(self) -> str:
        if self._ws is not None:
            try:
                # Signal the end of audio so trailing finals are flushed before
                # the socket closes (universal streaming finalizes on this).
                await self._ws.send(b"")
            except Exception:
                logger.debug("AssemblyAI live end frame failed", exc_info=True)
            if self._receiver:
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(self._receiver, timeout=3.0)
            try:
                await self._ws.close()
            except Exception:
                logger.debug("AssemblyAI live close failed", exc_info=True)
        if self._receiver:
            try:
                await asyncio.wait_for(self._receiver, timeout=5)
            except TimeoutError:
                self._receiver.cancel()
        return normalize_persian_text(_compose(self._finals, self._partial))


class FireworksLiveSession(LiveSession):
    """Fireworks streaming ASR over WebSocket (PCM s16le 16 kHz)."""

    def __init__(self, config: dict[str, Any], emit: EmitFn):
        self.config = config
        self.emit = emit
        # No PCM is buffered here (see AssemblyAILiveSession).
        self._finals: list[str] = []
        self._final_segments: dict[int, str] = {}
        self._partial = ""
        self._ws = None
        self._receiver: asyncio.Task | None = None

    async def start(self) -> None:
        try:
            import websockets
        except ImportError as error:
            raise ValueError(
                "Fireworks live transcription requires the websockets package"
            ) from error

        api_key = str(self.config.get("ASR_KEY") or self.config.get("WHISPER_KEY") or "").strip()
        if not api_key:
            raise ValueError("A Fireworks API key is required for live transcription")

        info = ASR_PROVIDERS["fireworks"]
        model = str(self.config.get("ASR_MODEL") or config_model(self.config) or "fireworks-asr-v2")
        url = info.get("streaming_url_v2") if "v2" in model else info.get("streaming_url")
        # Fireworks streaming expects an explicit language query parameter;
        # ``auto`` is a Batch-only value, so map it to the app primary language.
        language = streaming_asr_language(self.config)
        params = [f"language={language}"]
        if model:
            params.append(f"model={model}")
        url = f"{url}?{'&'.join(params)}"

        headers = {"Authorization": f"Bearer {api_key}"}
        try:
            self._ws = await websockets.connect(
                url,
                additional_headers=headers,
                max_size=8 * 1024 * 1024,
            )
        except TypeError:
            # websockets <14 compatibility path (arg renamed in v14)
            self._ws = await websockets.connect(
                url,
                extra_headers=headers,
                max_size=8 * 1024 * 1024,
            )

        async def _receive() -> None:
            ws = self._ws
            assert ws is not None  # only reachable after start() assigned _ws above
            try:
                async for message in ws:
                    await self._handle_message(message)
            except Exception as error:
                logger.debug("Fireworks live receive ended: %s", error)

        self._receiver = asyncio.create_task(_receive())

    async def _handle_message(self, message: str | bytes) -> None:
        if isinstance(message, bytes):
            try:
                message = message.decode("utf-8")
            except UnicodeDecodeError:
                return
        try:
            payload = json.loads(message)
        except json.JSONDecodeError:
            return

        # Fireworks sends segments (``[{id, text, is_final, language}]``) with
        # each delta. Track finalized segments by id and treat the rest as the
        # running partial, so updates stay ordered and never regress.
        segments = payload.get("segments")
        if isinstance(segments, list) and segments:
            pending: list[str] = []
            for segment in segments:
                if not isinstance(segment, dict):
                    continue
                seg_text = str(segment.get("text") or "").strip()
                seg_id = segment.get("id")
                if not seg_text:
                    continue
                if segment.get("is_final") and seg_id is not None:
                    self._final_segments[int(seg_id)] = seg_text
                else:
                    pending.append(seg_text)
            finals_text = " ".join(
                self._final_segments[key] for key in sorted(self._final_segments)
            ).strip()
            self._finals = [finals_text] if finals_text else []
            self._partial = " ".join(pending).strip()
            emit_text = _compose(self._finals, self._partial)
            if self._partial:
                await self.emit({"type": "partial", "text": emit_text})
            else:
                await self.emit({"type": "final", "text": emit_text})
            return

        text = (
            payload.get("transcript") or payload.get("text") or payload.get("transcription") or ""
        )
        if not text and isinstance(payload.get("words"), list):
            text = " ".join(
                str(word.get("word") or word.get("text") or "")
                for word in payload["words"]
                if isinstance(word, dict)
            )
        if not text:
            return
        is_final = bool(
            payload.get("is_final") or payload.get("final") or payload.get("type") == "final"
        )
        if is_final:
            self._finals.append(text)
            self._partial = ""
            await self.emit({"type": "final", "text": _compose(self._finals, "")})
        else:
            self._partial = text
            await self.emit({"type": "partial", "text": _compose(self._finals, text)})

    async def feed_pcm(self, pcm: bytes) -> None:
        if self._ws is not None:
            await self._ws.send(pcm)

    async def stop(self) -> str:
        if self._ws is not None:
            try:
                # Fireworks finalizes pending segments on this checkpoint.
                await self._ws.send(json.dumps({"checkpoint_id": "final"}))
            except Exception:
                logger.debug("Fireworks live end frame failed", exc_info=True)
            # Give the trailing finals a moment to arrive before closing.
            if self._receiver:
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(self._receiver, timeout=2.0)
            try:
                await self._ws.close()
            except Exception:
                logger.debug("Fireworks live close failed", exc_info=True)
        if self._receiver:
            try:
                await asyncio.wait_for(self._receiver, timeout=5)
            except TimeoutError:
                self._receiver.cancel()
        return normalize_persian_text(_compose(self._finals, self._partial))


class RollingWindowLiveSession(LiveSession):
    """Approximate live captions by re-transcribing a rolling PCM window."""

    def __init__(self, config: dict[str, Any], emit: EmitFn):
        self.config = config
        self.emit = emit
        self._pcm = bytearray()
        self._last_emit = 0.0
        self._busy = False
        self._latest = ""
        self._lock = asyncio.Lock()

    async def feed_pcm(self, pcm: bytes) -> None:
        self._pcm.extend(pcm)
        now = time.monotonic()
        window_bytes = int(ROLLING_WINDOW_SECONDS * SAMPLE_RATE * 2)
        hop_bytes = int(ROLLING_HOP_SECONDS * SAMPLE_RATE * 2)
        cap_bytes = int(ROLLING_BUFFER_SECONDS * SAMPLE_RATE * 2)
        if len(self._pcm) > cap_bytes:
            # Only the tail is ever transcribed; keep a bounded window instead
            # of the whole recording (~115 MB/hour at 16 kHz s16le).
            del self._pcm[:-cap_bytes]
        if len(self._pcm) < hop_bytes:
            return
        if now - self._last_emit < ROLLING_HOP_SECONDS or self._busy:
            return
        self._last_emit = now
        window = bytes(self._pcm[-window_bytes:])
        asyncio.create_task(self._transcribe_window(window))

    async def _transcribe_window(self, window: bytes) -> None:
        from server.transcription.audio import transcribe_audio

        async with self._lock:
            self._busy = True
            try:
                wav = pcm_to_wav(window)
                result = await transcribe_audio(wav)
                text = str(result.get("text") or "").strip()
                if text:
                    self._latest = text
                    await self.emit({"type": "partial", "text": text})
            except Exception as error:
                logger.debug("Rolling-window live transcription failed: %s", error)
            finally:
                self._busy = False

    async def stop(self) -> str:
        if self._pcm:
            from server.transcription.audio import transcribe_audio

            try:
                result = await transcribe_audio(pcm_to_wav(bytes(self._pcm)))
                self._latest = str(result.get("text") or self._latest)
            except Exception as error:
                logger.debug("Rolling-window final transcription failed: %s", error)
        return normalize_persian_text(self._latest)


def config_model(config: dict[str, Any]) -> str:
    return str(config.get("ASR_MODEL") or config.get("WHISPER_MODEL") or "")


def _compose(finals: list[str], partial: str) -> str:
    parts = [part.strip() for part in finals if part and part.strip()]
    if partial.strip():
        parts.append(partial.strip())
    return normalize_persian_text(" ".join(parts))


def create_live_session(config: dict[str, Any], emit: EmitFn) -> LiveSession:
    """Pick the best live adapter for the configured ASR provider."""
    connection = resolve_asr_connection(config)
    protocol = connection["protocol"]
    model = connection["model"]
    if protocol == "speechmatics":
        return SpeechmaticsLiveSession(config, emit)
    if protocol == "assemblyai":
        return AssemblyAILiveSession(config, emit)
    if protocol == "fireworks" and not str(model).startswith("whisper-"):
        return FireworksLiveSession(config, emit)
    return RollingWindowLiveSession(config, emit)


def live_is_authoritative(config: dict[str, Any]) -> bool:
    """Native streaming providers produce a complete transcript; rolling windows do not."""
    connection = resolve_asr_connection(config)
    protocol = connection["protocol"]
    model = connection["model"]
    return protocol in ("speechmatics", "assemblyai") or (
        protocol == "fireworks" and not str(model).startswith("whisper-")
    )
