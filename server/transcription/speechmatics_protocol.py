"""Speechmatics Realtime protocol facts: limits, message catalogs, error text.

Everything here is transcribed from the documented Realtime API contract
(``wss://…/v2/``): the ``transcription_config`` value ranges, the in-band
``Error`` / ``Warning`` / ``Info`` type tables, and the WebSocket close codes
that follow an in-band error.

Keeping the protocol facts in one module has two purposes:

* the live adapter (``server/transcription/live.py``) stays readable and only
  deals with the session lifecycle, and
* the facts are unit-testable without opening a socket, so a change in a
  documented range (for example ``max_delay``) fails a test instead of a
  clinician's recording.

Session tuning is read from the process environment (``ASR_LIVE_*``) or from
the config dict when the desktop app starts to persist it; see
``live_settings``. Both paths are clamped to the documented ranges, so a
typo in an environment variable cannot start an invalid session.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

# --------------------------------------------------------------------------
# Documented transcription_config limits (Realtime API reference).
# --------------------------------------------------------------------------
MAX_DELAY_MIN_SECONDS = 0.7
MAX_DELAY_MAX_SECONDS = 4.0
MAX_DELAY_DEFAULT_SECONDS = 1.0
MAX_DELAY_MODE_DEFAULT = "flexible"
MAX_DELAY_MODES = frozenset({"flexible", "fixed"})

# ``conversation_config.end_of_utterance_silence_trigger``: 0 disables turn
# detection, anything above 2 is rejected by the service.
END_OF_UTTERANCE_TRIGGER_MIN_SECONDS = 0.0
END_OF_UTTERANCE_TRIGGER_MAX_SECONDS = 2.0
END_OF_UTTERANCE_TRIGGER_DEFAULT_SECONDS = 0.8

PUNCTUATION_SENSITIVITY_MIN = 0.0
PUNCTUATION_SENSITIVITY_MAX = 1.0
PUNCTUATION_SENSITIVITY_DEFAULT = 0.5

# ``speaker_diarization_config.max_speakers`` must be >= 2 when set.
MAX_SPEAKERS_MIN = 2
MAX_SPEAKERS_DEFAULT = 4

# ``additional_vocab`` is documented to add up to ~15 s of session-start
# latency ("you should expect a delay of up to 15 seconds"). The SDK waits only
# 5 s for RecognitionStarted, so a session that sends a vocabulary needs a
# longer start budget than one that does not.
ADDITIONAL_VOCAB_START_BUDGET_SECONDS = 15.0
START_TIMEOUT_SECONDS = 15.0
START_TIMEOUT_WITH_VOCAB_SECONDS = START_TIMEOUT_SECONDS + ADDITIONAL_VOCAB_START_BUDGET_SECONDS
# Grace on top of the SDK's own start wait before we declare the session dead.
START_GRACE_SECONDS = 5.0

# --------------------------------------------------------------------------
# Transport tuning (not part of the wire protocol).
# --------------------------------------------------------------------------
# The service documents that it may read audio slower than the client sends it
# and that overrun closes the connection "with prejudice". A bounded queue
# turns that into observable backpressure instead of unbounded memory growth.
# 512 browser frames (~8 KB each at 16 kHz s16le) ≈ 2 minutes of audio.
AUDIO_QUEUE_MAX_FRAMES = 512
# How long feed_pcm() may block on a full queue before the session is treated
# as stalled. Realtime capture produces a frame every ~256 ms, so 30 s means
# the engine is roughly two minutes behind.
AUDIO_QUEUE_PUT_TIMEOUT_SECONDS = 30.0
# AudioAdded confirms every AddAudio; no acknowledgement for this long while
# audio is flowing means the session is dead even if the socket is open.
AUDIO_ACK_STALL_SECONDS = 60.0
# ForceEndOfUtterance / EndOfStream flush budgets during stop().
FLUSH_TIMEOUT_SECONDS = 3.0
DRAIN_TIMEOUT_SECONDS = 15.0

# --------------------------------------------------------------------------
# WebSocket close codes documented to follow an in-band error.
# --------------------------------------------------------------------------
CLOSE_CODE_PAYLOADS: dict[int, str] = {
    1003: "protocol_error",
    1008: "policy_violation",
    1011: "internal_error",
    4001: "not_authorised",
    4003: "not_allowed",
    4004: "invalid_model",
    4005: "quota_exceeded",
    4006: "timelimit_exceeded",
    4013: "job_error",
}

# The API reference recommends a client retry interval of at least 5-10 s for
# exactly these failures. We fail fast (the app falls back to batch
# transcription of the full recording) but still tell the user that retrying
# shortly is worthwhile.
RETRYABLE_ERROR_TYPES = frozenset({"quota_exceeded", "job_error", "internal_error"})

# Recommended minimum retry interval, documented for the codes above.
RETRY_BACKOFF_SECONDS = 5.0

ERROR_MESSAGES: dict[str, str] = {
    "invalid_message": "The realtime service rejected a control message (invalid_message).",
    "invalid_model": (
        "The selected model is not available for live transcription with this "
        "language or account (invalid_model)."
    ),
    "invalid_language": (
        "The selected language is not supported for live transcription (invalid_language)."
    ),
    "invalid_config": "The realtime service rejected the session configuration (invalid_config).",
    "invalid_audio_type": "The audio format was rejected by the realtime service (invalid_audio_type).",
    "invalid_output_format": (
        "The output format was rejected by the realtime service (invalid_output_format)."
    ),
    "not_authorised": "The Speechmatics API key was rejected (not_authorised).",
    "not_allowed": "This account may not start realtime sessions (not_allowed).",
    "job_error": "The realtime service could not run this session (job_error). Retry shortly.",
    "protocol_error": "Realtime messages arrived in an unexpected order (protocol_error).",
    "quota_exceeded": (
        "The concurrent-session quota for this account is full (quota_exceeded). Retry shortly."
    ),
    "timelimit_exceeded": "The account's transcription time quota is used up (timelimit_exceeded).",
    "idle_timeout": "The session was closed after an hour without audio (idle_timeout).",
    "session_timeout": "The session reached the 48-hour maximum duration (session_timeout).",
    "unknown_error": "The realtime service reported an unspecified error (unknown_error).",
    # Locally detected failures (not service error types).
    "internal_error": "The realtime service closed the connection (internal_error). Retry shortly.",
    "audio_stalled": (
        "The realtime service stopped acknowledging audio, so the live session was closed "
        "to protect the rest of the recording (audio_stalled). Retry shortly."
    ),
    "transport_error": "The realtime connection was lost.",
}

WARNING_MESSAGES: dict[str, str] = {
    "duration_limit_exceeded": (
        "The utterance exceeded the realtime duration limit; the service is finishing the "
        "session early and the remaining audio is ignored."
    ),
    "unsupported_translation_pair": "A requested translation language pair is unsupported.",
    "empty_translation_target_list": "No supported translation targets; translation will not run.",
    "idle_timeout": "The session will time out soon because no audio has been sent.",
    "session_timeout": "The session is approaching the 48-hour maximum duration.",
    "add_audio_after_eos": "Audio sent after the end of the stream was ignored.",
    "speaker_id": "Speaker identification reported a problem.",
}

INFO_MESSAGES: dict[str, str] = {
    "recognition_quality": "The realtime engine reported its audio-quality model.",
    "concurrent_session_usage": "The realtime engine reported concurrent-session usage.",
}


@dataclass(frozen=True)
class ErrorInfo:
    """A classified realtime failure."""

    error_type: str
    message: str
    reason: str
    code: int | None
    retryable: bool
    close_code: int | None = None


def parse_bool(value: Any) -> bool | None:
    """Parse a truthy/falsy setting; ``None`` means 'not configured'."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on", "enabled"}:
        return True
    if text in {"0", "false", "no", "off", "disabled"}:
        return False
    return None


def parse_float(value: Any) -> float | None:
    """Parse a numeric setting; ``None`` means 'not configured or invalid'."""
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def parse_int(value: Any) -> int | None:
    """Parse an integer setting; ``None`` means 'not configured or invalid'."""
    parsed = parse_float(value)
    if parsed is None:
        return None
    return int(parsed)


def clamp(value: float | None, low: float, high: float, default: float) -> float:
    """Clamp ``value`` into ``[low, high]``; fall back to ``default``."""
    if value is None:
        return default
    return max(low, min(high, value))


def _setting(config: dict[str, Any] | None, name: str) -> Any:
    """Read a live-session setting from the config dict, then the environment."""
    if config and config.get(name) not in (None, ""):
        return config.get(name)
    return os.environ.get(name)


@dataclass(frozen=True)
class LiveSettings:
    """Validated realtime session tuning, clamped to documented ranges."""

    max_delay: float
    max_delay_mode: str
    end_of_utterance_trigger: float
    remove_disfluencies: bool
    punctuation_sensitivity: float
    diarization: bool
    max_speakers: int

    @property
    def turn_detection_enabled(self) -> bool:
        return self.end_of_utterance_trigger > 0

    def as_features(self) -> dict[str, Any]:
        """Feature summary reported to the client in the ``ready`` frame."""
        return {
            "max_delay": self.max_delay,
            "turn_detection": self.turn_detection_enabled,
            "remove_disfluencies": self.remove_disfluencies,
            "diarization": self.diarization,
        }


def live_settings(config: dict[str, Any] | None = None) -> LiveSettings:
    """Build validated live-session settings from config/environment.

    Every value is clamped to the documented range, so an out-of-range
    ``ASR_LIVE_MAX_DELAY`` cannot make the service reject the session with
    ``invalid_config`` before any audio is accepted.
    """
    config = config or {}
    mode = str(_setting(config, "ASR_LIVE_MAX_DELAY_MODE") or "").strip().lower()
    sensitivity = parse_float(_setting(config, "ASR_LIVE_PUNCTUATION_SENSITIVITY"))
    return LiveSettings(
        max_delay=clamp(
            parse_float(_setting(config, "ASR_LIVE_MAX_DELAY")),
            MAX_DELAY_MIN_SECONDS,
            MAX_DELAY_MAX_SECONDS,
            MAX_DELAY_DEFAULT_SECONDS,
        ),
        max_delay_mode=mode if mode in MAX_DELAY_MODES else MAX_DELAY_MODE_DEFAULT,
        end_of_utterance_trigger=clamp(
            parse_float(_setting(config, "ASR_LIVE_END_OF_UTTERANCE_TRIGGER")),
            END_OF_UTTERANCE_TRIGGER_MIN_SECONDS,
            END_OF_UTTERANCE_TRIGGER_MAX_SECONDS,
            END_OF_UTTERANCE_TRIGGER_DEFAULT_SECONDS,
        ),
        remove_disfluencies=bool(parse_bool(_setting(config, "ASR_LIVE_REMOVE_DISFLUENCIES"))),
        punctuation_sensitivity=clamp(
            sensitivity,
            PUNCTUATION_SENSITIVITY_MIN,
            PUNCTUATION_SENSITIVITY_MAX,
            PUNCTUATION_SENSITIVITY_DEFAULT,
        ),
        diarization=bool(parse_bool(_setting(config, "ASR_LIVE_DIARIZATION"))),
        max_speakers=max(
            MAX_SPEAKERS_MIN,
            parse_int(_setting(config, "ASR_LIVE_MAX_SPEAKERS")) or MAX_SPEAKERS_DEFAULT,
        ),
    )


def is_retryable(error_type: str) -> bool:
    """Whether the documented retry guidance applies to this error type."""
    return error_type in RETRYABLE_ERROR_TYPES


def error_message(error_type: str, reason: str = "") -> str:
    """Human-readable text for an in-band ``Error`` (or a locally detected one)."""
    base = ERROR_MESSAGES.get(error_type, f"The realtime service reported '{error_type}'.")
    reason = (reason or "").strip()
    if reason and reason.lower() != error_type:
        return f"{base} Service reason: {reason}"
    return base


def warning_message(warning_type: str, reason: str = "") -> str:
    """Human-readable text for an in-band ``Warning``."""
    reason = (reason or "").strip()
    if reason:
        return reason
    return WARNING_MESSAGES.get(warning_type, f"The realtime service warned '{warning_type}'.")


def close_payload(close_code: int | None) -> str | None:
    """Documented close payload for a WebSocket close code, if any."""
    if close_code is None:
        return None
    return CLOSE_CODE_PAYLOADS.get(int(close_code))


def classify_error(
    error_type: str = "",
    reason: str = "",
    code: int | None = None,
) -> ErrorInfo:
    """Classify an in-band ``Error`` message into a client-facing event payload."""
    error_type = (error_type or "").strip() or "unknown_error"
    payload_type = close_payload(code)
    if payload_type and not error_type:
        error_type = payload_type
    return ErrorInfo(
        error_type=error_type,
        message=error_message(error_type, reason),
        reason=reason,
        code=code,
        retryable=is_retryable(error_type),
        close_code=code,
    )


def classify_close(close_code: int | None, payload: str = "") -> ErrorInfo:
    """Classify a bare WebSocket close (no in-band ``Error`` was received)."""
    payload_type = close_payload(close_code) or (payload or "").strip() or "transport_error"
    detail = f"close code {close_code}" if close_code is not None else "closed by peer"
    return ErrorInfo(
        error_type=payload_type,
        message=f"{error_message(payload_type)} ({detail})",
        reason=payload,
        code=close_code,
        retryable=is_retryable(payload_type),
        close_code=close_code,
    )


def dominant_speaker(results: Any) -> str | None:
    """Return the speaker label covering most words of a transcript segment.

    ``AddTranscript.results[].alternatives[0].speaker`` is only populated when
    diarization is enabled. A segment can straddle a speaker change, so the
    label with the most words wins; ties keep the first label seen.
    """
    if not isinstance(results, list):
        return None
    counts: dict[str, int] = {}
    order: list[str] = []
    for result in results:
        alternatives = getattr(result, "alternatives", None)
        if not alternatives:
            continue
        speaker = getattr(alternatives[0], "speaker", None)
        if not speaker:
            continue
        speaker = str(speaker)
        if speaker not in counts:
            order.append(speaker)
        counts[speaker] = counts.get(speaker, 0) + 1
    if not counts:
        return None
    best = max(counts.values())
    for speaker in order:
        if counts[speaker] == best:
            return speaker
    return None
