"""Live / real-time speech-to-text adapters.

Native streaming:
- Speechmatics Realtime with ``enable_partials``
- Fireworks Audio Streaming WebSocket

Fallback for batch-only engines (Whisper.cpp, OpenAI Audio, Parakeet,
Shenava, custom OpenAI-compatible ASR): rolling WAV windows over the
in-progress PCM buffer.
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import time
import wave
from collections.abc import Awaitable, Callable
from typing import Any

from server.transcription.language import normalize_persian_text, resolve_asr_language
from server.utils.providers import ASR_PROVIDERS, resolve_asr_connection

logger = logging.getLogger(__name__)

EmitFn = Callable[[dict[str, Any]], Awaitable[None]]

SAMPLE_RATE = 16000
ROLLING_WINDOW_SECONDS = 5.0
ROLLING_HOP_SECONDS = 1.5


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

    async def stop(self) -> str:
        return ""


class SpeechmaticsLiveSession(LiveSession):
    """Speechmatics Realtime with partial transcripts enabled."""

    def __init__(self, config: dict[str, Any], emit: EmitFn):
        self.config = config
        self.emit = emit
        self._pcm = bytearray()
        self._finals: list[str] = []
        self._partial = ""
        self._client = None
        self._task: asyncio.Task | None = None
        self._queue: asyncio.Queue[bytes | None] = asyncio.Queue()

    async def start(self) -> None:
        try:
            from speechmatics.rt import (
                AsyncClient,
                AudioEncoding,
                AudioFormat,
                Model,
                ServerMessageType,
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

        language = resolve_asr_language(self.config)
        speechmatics_language = "auto" if language == "auto" else language
        # Map the configured operating point onto the v1 ``Model`` enum; any
        # unrecognised value falls back to the default ``enhanced`` model.
        model_name = str(self.config.get("ASR_MODEL") or "enhanced").strip().lower()
        model = Model.STANDARD if model_name == "standard" else Model.ENHANCED

        client_url = str(self.config.get("ASR_BASE_URL") or "").strip() or None
        client = AsyncClient(api_key=api_key, url=client_url)
        self._client = client

        async def handle_partial(message: dict) -> None:
            try:
                result = TranscriptResult.from_message(message)
                text = result.metadata.transcript
            except (KeyError, TypeError, AttributeError):
                text = ""
            if text:
                self._partial = text
                await self.emit({"type": "partial", "text": _compose(self._finals, text)})

        async def handle_final(message: dict) -> None:
            try:
                result = TranscriptResult.from_message(message)
                text = result.metadata.transcript
            except (KeyError, TypeError, AttributeError):
                text = ""
            if text:
                self._finals.append(text)
                self._partial = ""
                await self.emit({"type": "final", "text": _compose(self._finals, "")})

        # speechmatics-rt callbacks may be sync; wrap if needed.
        def on_partial(message: dict) -> None:
            asyncio.create_task(handle_partial(message))

        def on_final(message: dict) -> None:
            asyncio.create_task(handle_final(message))

        partial_event = ServerMessageType.ADD_PARTIAL_TRANSCRIPT
        client.on(partial_event, on_partial)
        client.on(ServerMessageType.ADD_TRANSCRIPT, on_final)

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
                await client.transcribe(
                    _QueueAudio(self._queue),  # ty: ignore (SDK types `source` as BinaryIO but accepts any binary read()-able object, incl. async reads)
                    transcription_config=TranscriptionConfig(
                        language=speechmatics_language,
                        model=model,
                        enable_partials=True,
                    ),
                    audio_format=AudioFormat(
                        encoding=AudioEncoding.PCM_S16LE,
                        sample_rate=SAMPLE_RATE,
                        chunk_size=4096,
                    ),
                    timeout=None,
                )
            except Exception as error:
                logger.error("Speechmatics live session failed: %s", error)
                await self.emit({"type": "error", "message": str(error)})

        self._task = asyncio.create_task(_run())

    async def feed_pcm(self, pcm: bytes) -> None:
        self._pcm.extend(pcm)
        await self._queue.put(pcm)

    async def stop(self) -> str:
        await self._queue.put(None)
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=15)
            except TimeoutError:
                self._task.cancel()
        if self._client is not None:
            try:
                await self._client.close()
            except Exception:
                logger.debug("Speechmatics live client close failed", exc_info=True)
        return normalize_persian_text(_compose(self._finals, self._partial))


class FireworksLiveSession(LiveSession):
    """Fireworks streaming ASR over WebSocket (PCM s16le 16 kHz)."""

    def __init__(self, config: dict[str, Any], emit: EmitFn):
        self.config = config
        self.emit = emit
        self._pcm = bytearray()
        self._finals: list[str] = []
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
        language = resolve_asr_language(self.config)
        params = []
        if language != "auto":
            params.append(f"language={language}")
        if model:
            params.append(f"model={model}")
        if params:
            url = f"{url}?{'&'.join(params)}"

        headers = {"Authorization": f"Bearer {api_key}"}
        try:
            self._ws = await websockets.connect(
                url,  # ty: ignore (websockets>=14 arg name; older versions fall back below)
                additional_headers=headers,
                max_size=8 * 1024 * 1024,
            )
        except TypeError:
            self._ws = await websockets.connect(
                url,  # ty: ignore (websockets<14 arg name kept for compat)
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
        self._pcm.extend(pcm)
        if self._ws is not None:
            await self._ws.send(pcm)

    async def stop(self) -> str:
        if self._ws is not None:
            try:
                await self._ws.send(json.dumps({"type": "end"}))
            except Exception:
                logger.debug("Fireworks live end frame failed", exc_info=True)
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
    if protocol == "fireworks" and not str(model).startswith("whisper-"):
        return FireworksLiveSession(config, emit)
    return RollingWindowLiveSession(config, emit)


def live_is_authoritative(config: dict[str, Any]) -> bool:
    """Native streaming providers produce a complete transcript; rolling windows do not."""
    connection = resolve_asr_connection(config)
    protocol = connection["protocol"]
    model = connection["model"]
    return protocol == "speechmatics" or (
        protocol == "fireworks" and not str(model).startswith("whisper-")
    )
