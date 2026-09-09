"""Neural voice-activity detection (Silero VAD) for file transcription — W2.2.

``trim_with_silero`` is a drop-in alternative to the energy-based
``trim_silence_wav`` with the *same fail-open contract*: any problem
(missing extra, missing weights, undecodable audio, no voiced frames)
returns the input buffer unchanged so a broken VAD can never break
transcription.

Strategy selection lives in ``hygiene.prepare_audio`` (``PHLOX_VAD``):

* ``auto`` (default) — Silero when available, else the energy VAD.
* ``silero``         — force Silero; falls back to energy when unavailable.
* ``energy``         — the exact pre-W2.2 behavior.
* ``off``            — no trimming at all (A/B baseline).

Weights are a tiny ONNX artifact (~2 MB) fetched through the same
model-download manager used for the ASR bundles; the download is attempted
at most once per process and every failure degrades to the energy path.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import io
import logging
import math
import os
import wave

logger = logging.getLogger(__name__)

_SILERO_ARTIFACT_ID = "silero-vad"
_SILERO_THRESHOLD_DEFAULT = 0.5
_MARGIN_MS = 200  # keep some breath before/after trimmed speech
_MIN_REMOVED_MS = 500  # below this, rewriting the container is not worth it
_CHUNK_16K = 512  # Silero window at 16 kHz (32 ms)
_DOWNLOAD_TIMEOUT_SECONDS = 15

# One best-effort download attempt per process; failures stay silent.
_DOWNLOAD_ATTEMPTED = False


def _env_threshold() -> float:
    try:
        value = float(os.environ.get("PHLOX_VAD_THRESHOLD", _SILERO_THRESHOLD_DEFAULT))
    except (TypeError, ValueError):
        return _SILERO_THRESHOLD_DEFAULT
    return min(0.9, max(0.1, value))


def vad_strategy() -> str:
    """Validated ``PHLOX_VAD`` value (default ``auto``)."""
    raw = str(os.environ.get("PHLOX_VAD", "auto")).strip().lower()
    return raw if raw in {"auto", "silero", "energy", "off"} else "auto"


def _silero_weights_path():
    """Local Silero ONNX path after one best-effort download attempt."""
    global _DOWNLOAD_ATTEMPTED
    from server.utils.whisper_models import aux_model_manager

    path = aux_model_manager.get_path(_SILERO_ARTIFACT_ID)
    if path is not None or _DOWNLOAD_ATTEMPTED:
        return path
    _DOWNLOAD_ATTEMPTED = True
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(
                asyncio.run, aux_model_manager.ensure_downloaded(_SILERO_ARTIFACT_ID)
            )
            path = future.result(timeout=_DOWNLOAD_TIMEOUT_SECONDS)
    except Exception:  # noqa: BLE001 — VAD must never break ASR
        logger.debug("Silero VAD weights unavailable; energy VAD will be used", exc_info=True)
        path = None
    return path


def silero_available() -> bool:
    """True when numpy/onnxruntime and the Silero weights are usable."""
    try:
        import importlib.util

        if (
            importlib.util.find_spec("numpy") is None
            or importlib.util.find_spec("onnxruntime") is None
        ):
            return False
    except (ImportError, ValueError):
        return False
    return _silero_weights_path() is not None


def _load_silero_session():
    """Load the ONNX session once; None when the runtime is unavailable."""
    path = _silero_weights_path()
    if path is None:
        return None
    try:
        import onnxruntime as ort
    except ImportError:
        return None
    return ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])


def _silero_speech_probs(session, pcm: bytes, rate: int) -> list[float]:
    """Per-chunk speech probabilities from the Silero graph."""
    import numpy as np

    samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
    chunk = _CHUNK_16K
    input_name = state_name = sr_name = None
    state_shape: list[int] = []
    for item in session.get_inputs():
        lowered = item.name.lower()
        if lowered == "input":
            input_name = item.name
        elif "state" in lowered:
            state_name = item.name
            state_shape = [dim if isinstance(dim, int) and dim > 0 else 1 for dim in item.shape]
        else:
            sr_name = item.name
    if input_name is None:
        raise ValueError("Silero model has no audio input")
    state = np.zeros(state_shape or [2, 1, 64], dtype=np.float32)
    sr_value = np.array([rate], dtype=np.int64)

    probs: list[float] = []
    output_names = [o.name for o in session.get_outputs()]
    state_output = next((n for n in output_names if "state" in n.lower()), None)
    for start in range(0, max(1, samples.size), chunk):
        frame = samples[start : start + chunk]
        if frame.size < chunk:
            frame = np.pad(frame, (0, chunk - frame.size))
        feed = {input_name: frame[None, :]}
        if sr_name is not None:
            feed[sr_name] = sr_value
        if state_name is not None:
            feed[state_name] = state
        outputs = session.run(None, feed)
        prob = float(np.asarray(outputs[0]).reshape(-1)[0])
        probs.append(prob)
        if state_output is not None:
            state = np.asarray(outputs[output_names.index(state_output)])
    return probs


def _read_mono_wav(audio_bytes: bytes) -> tuple[bytes, int] | None:
    """Mono 16-bit PCM frames + rate, or None when not decodable."""
    import array

    try:
        with wave.open(io.BytesIO(audio_bytes), "rb") as wav:
            if wav.getcomptype() != "NONE" or wav.getsampwidth() != 2:
                return None
            rate = wav.getframerate()
            channels = wav.getnchannels()
            frames = wav.readframes(wav.getnframes())
    except (wave.Error, EOFError):
        return None
    if channels == 1:
        return frames, rate
    samples = array.array("h")
    samples.frombytes(frames[: (len(frames) // 2) * 2])
    mono = array.array(
        "h",
        (
            (left + right) // 2
            for left, right in zip(samples[::channels], samples[1::channels], strict=False)
        ),
    )
    return mono.tobytes(), rate


def _slice_wav(frames: bytes, rate: int, start_sample: int, end_sample: int) -> bytes:
    out = io.BytesIO()
    with wave.open(out, "wb") as wav_out:
        wav_out.setnchannels(1)
        wav_out.setsampwidth(2)
        wav_out.setframerate(rate)
        wav_out.writeframes(frames[start_sample * 2 : end_sample * 2])
    return out.getvalue()


def trim_with_silero(audio_bytes: bytes, session=None) -> tuple[bytes, dict]:
    """Trim leading/trailing silence with the Silero VAD.

    Returns ``(bytes, {"trimmed_ms": int})`` exactly like
    ``trim_silence_wav``; the original bytes are returned whenever anything
    is off — including the mandatory "no voiced frames ⇒ return original"
    behavior. Never raises. The meta carries ``silero_ran: True`` whenever
    the model actually processed the audio, so callers can tell "Silero saw
    nothing to trim" apart from "Silero was unavailable".
    """
    try:
        if session is None:
            session = _load_silero_session()
        if session is None:
            return audio_bytes, {"trimmed_ms": 0}
        decoded = _read_mono_wav(audio_bytes)
        if decoded is None:
            return audio_bytes, {"trimmed_ms": 0}
        frames, rate = decoded
        if rate != 16000 or not frames:
            # Silero expects 16 kHz; prepare_audio already transcodes files
            # to that rate, so anything else is an unexpected shape: keep it.
            return audio_bytes, {"trimmed_ms": 0}

        probs = _silero_speech_probs(session, frames, rate)
        threshold = _env_threshold()
        voiced = [i for i, prob in enumerate(probs) if prob >= threshold]
        if not voiced:
            # Never drop the only audio: "no voiced frames" keeps the input.
            return audio_bytes, {"trimmed_ms": 0, "silero_ran": True}

        chunk_ms = _CHUNK_16K / rate * 1000.0
        margin = max(1, math.ceil(_MARGIN_MS / chunk_ms))
        first = max(0, voiced[0] - margin)
        last = min(len(probs) - 1, voiced[-1] + margin)
        removed_ms = int((first + (len(probs) - 1 - last)) * chunk_ms)
        if removed_ms < _MIN_REMOVED_MS:
            return audio_bytes, {"trimmed_ms": 0, "silero_ran": True}

        start_sample = first * _CHUNK_16K
        end_sample = min(len(frames) // 2, (last + 1) * _CHUNK_16K)
        return _slice_wav(frames, rate, start_sample, end_sample), {
            "trimmed_ms": removed_ms,
            "silero_ran": True,
        }
    except Exception:  # noqa: BLE001 — VAD must never break ASR
        logger.debug("Silero VAD trim skipped", exc_info=True)
        return audio_bytes, {"trimmed_ms": 0}
