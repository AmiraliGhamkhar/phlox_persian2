"""ASR output hygiene: silence trimming, artifact flags and confidence classes.

Rationale (see docs/phlox-accuracy-hallucination-plan.md, refs A1/A4/A5):

* Whisper family models hallucinate most strongly on silence and non-speech
  spans; leading/trailing silences are a direct trigger. An energy-based VAD
  pre-pass that trims them is the cheapest high-impact mitigation.
* Whisper also re-emits training artifacts ("Subtitles by …", channel
  outros) and loops. Such segments should be *flagged for review*, not
  silently deleted: clinical safety prefers a false alarm over a silent
  deletion of real speech.
* verbose_json already carries avg_logprob / no_speech_prob per segment;
  we classify segments so downstream UI can amber-flag weak evidence.

No heavy dependencies: the VAD operates on uncompressed 16-bit PCM WAV
bytes directly; other containers are passed through untouched unless
ffmpeg happens to be available.
"""

from __future__ import annotations

import io
import logging
import math
import os
import re
import shutil
import subprocess
import wave
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Segment confidence classification thresholds (tunable via env for field
# tuning without code changes; values follow the practical ranges used in
# whisper.cpp/faster-whisper community guidance).
_LOW_LOGPROB_DEFAULT = -0.85  # avg_logprob below this is low confidence
_NO_SPEECH_DEFAULT = 0.65  # no_speech_prob above this is suspect

# Frame size used by the energy VAD.
_VAD_FRAME_MS = 30
_VAD_KEEP_MARGIN_MS = 200  # keep some breath before/after trimmed speech

# Common non-clinical artifacts Whisper emits on silence, media files or
# training-data bleed. Whole-segment near-matches become flags (never
# silent deletions). Keep this list conservative and high-precision.
_HALLUCINATION_PATTERNS = [
    # English media/caption artifacts
    r"^thanks? for watching",
    r"^subscribe to( our| my)? channel",
    r"^subtitles? (by|from)",
    r"^(you|like)\s+(and\s+subscribe)\s+to\s+our\s+channel",
    r"^♪|^\[music\]$|^\[applause\]$|^\[silence\]$",
    r"^please (like|subscribe)",
    r"^don'?t forget to (like|subscribe)",
    r"^ok\s+ok\s+ok\s+ok",
    # Named backreference: plain \1 would bind to an earlier capture group
    # once the alternatives are joined into one big regex.
    r"^\s*(?P<filler>mmm|oh|uh|ah)(?:\s+(?P=filler))+\s*[.!]?\s*$",
    # Persian caption/YouTube artifacts seen in Whisper output
    r"^با تشکر از (توجه|مشاهده) (شما)?\.?$",
    r"^زیرنویس( توسط)?",
    r"^لطفاً (لایک و سابسکرایب|سابسکرایب و لایک)",
    r"^فراموش نکنید که (لایک|سابسکرایب)",
    r"^\s*[•*\-]\s*$",
]
_HALLUCINATION_RE = re.compile(
    "|".join(f"(?:{p})" for p in _HALLUCINATION_PATTERNS),
    re.IGNORECASE | re.MULTILINE,
)

# Repetition loop: same short token run repeated 4+ times.
_LOOP_RE = re.compile(r"(?:\b([\w؀-ۿ]{1,20})\b(?:\s+\1\b){3,})", re.UNICODE)


@dataclass
class HygieneResult:
    text: str
    segments: list[dict] = field(default_factory=list)
    flags: list[dict] = field(default_factory=list)


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def classify_confidence(segment: dict) -> str:
    """Classify one verbose_json segment as 'ok' | 'low_confidence' | 'suspect'."""
    low_logprob = _env_float("PHLOX_ASR_LOW_LOGPROB", _LOW_LOGPROB_DEFAULT)
    no_speech = _env_float("PHLOX_ASR_NO_SPEECH_THRESH", _NO_SPEECH_DEFAULT)

    avg_logprob = segment.get("avg_logprob")
    no_speech_prob = segment.get("no_speech_prob")

    if isinstance(no_speech_prob, (int, float)) and no_speech_prob >= no_speech:
        return "suspect"
    if isinstance(avg_logprob, (int, float)) and avg_logprob <= low_logprob:
        return "low_confidence"
    return "ok"


def _rms(frame_bytes: bytes) -> float:
    """RMS of a 16-bit mono PCM chunk, normalised to 0..1."""
    count = len(frame_bytes) // 2
    if count <= 0:
        return 0.0
    total = 0
    import array

    samples = array.array("h")
    samples.frombytes(frame_bytes[: count * 2])
    for s in samples:
        total += s * s
    return math.sqrt(total / count) / 32768.0


def _is_wav(audio_bytes: bytes) -> bool:
    return audio_bytes[:4] == b"RIFF" and audio_bytes[8:12] == b"WAVE"


def trim_silence_wav(audio_bytes: bytes) -> tuple[bytes, dict]:
    """Trim leading/trailing silence from a 16-bit PCM WAV buffer.

    Returns (bytes, {"trimmed_ms": int}) — original bytes are returned when
    the buffer cannot be parsed or is already tight. Never raises: a broken
    VAD must not break transcription (fail-open).
    """
    try:
        with wave.open(io.BytesIO(audio_bytes), "rb") as wav:
            if wav.getcomptype() != "NONE" or wav.getsampwidth() != 2:
                return audio_bytes, {"trimmed_ms": 0}
            rate = wav.getframerate()
            channels = wav.getnchannels()
            frames = wav.readframes(wav.getnframes())
        if channels > 1:
            import array

            samples = array.array("h")
            samples.frombytes(frames[: (len(frames) // 2) * 2])
            mono = array.array(
                "h",
                (
                    (left + right) // 2
                    for left, right in zip(samples[::channels], samples[1::channels], strict=False)
                ),
            )
            frames = mono.tobytes()
        # 16-bit mono frames for a 30 ms window (after downmix above).
        frame_bytes = max(2, int(rate * _VAD_FRAME_MS / 1000) * 2)
        energies = [
            _rms(frames[i : i + frame_bytes])
            for i in range(0, len(frames) - frame_bytes + 1, frame_bytes)
        ]
        if len(energies) < 5:
            return audio_bytes, {"trimmed_ms": 0}

        ordered = sorted(energies)
        floor = ordered[max(0, int(len(ordered) * 0.2))]
        threshold = max(floor * 3.0, floor + 0.004, 0.0025)
        voiced = [i for i, e in enumerate(energies) if e >= threshold]
        if not voiced:
            return audio_bytes, {"trimmed_ms": 0}

        margin = max(1, int(_VAD_KEEP_MARGIN_MS / _VAD_FRAME_MS))
        first = max(0, voiced[0] - margin)
        last = min(len(energies) - 1, voiced[-1] + margin)
        removed_ms = int((first + (len(energies) - 1 - last)) * _VAD_FRAME_MS)
        if removed_ms < 500:  # not worth rewriting the container
            return audio_bytes, {"trimmed_ms": 0}

        start = first * frame_bytes
        end = (last + 1) * frame_bytes + (len(frames) % frame_bytes)
        kept = frames[start:end]
        out = io.BytesIO()
        with wave.open(out, "wb") as wav_out:
            wav_out.setnchannels(1)
            wav_out.setsampwidth(2)
            wav_out.setframerate(rate)
            wav_out.writeframes(kept)
        return out.getvalue(), {"trimmed_ms": removed_ms}
    except Exception:  # noqa: BLE001 — VAD must never break ASR
        logger.debug("VAD trim skipped", exc_info=True)
        return audio_bytes, {"trimmed_ms": 0}


def maybe_transcode_to_wav(audio_bytes: bytes) -> bytes | None:
    """Decode non-WAV uploads to PCM WAV when ffmpeg is available (else None).

    Desktop installs ship ffmpeg next to the inference binaries; on systems
    without it we simply skip trimming rather than failing.
    """
    if _is_wav(audio_bytes):
        return audio_bytes
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return None
    try:
        result = subprocess.run(  # noqa: S603
            [
                ffmpeg,
                "-loglevel",
                "error",
                "-i",
                "pipe:0",
                "-f",
                "wav",
                "-ac",
                "1",
                "-ar",
                "16000",
                "-sample_fmt",
                "s16",
                "pipe:1",
            ],
            input=audio_bytes,
            capture_output=True,
            timeout=120,
            check=False,
        )
        if result.returncode == 0 and _is_wav(result.stdout):
            return result.stdout
    except (OSError, subprocess.SubprocessError):
        logger.debug("ffmpeg transcode for VAD skipped", exc_info=True)
    return None


def prepare_audio(audio_bytes: bytes) -> tuple[bytes, dict]:
    """Best-effort decode + silence trim. Fail-open: any problem returns input."""
    meta: dict = {"vad_applied": False, "trimmed_ms": 0}
    try:
        decoded = maybe_transcode_to_wav(audio_bytes)
        if decoded is None:
            return audio_bytes, meta
        trimmed, info = trim_silence_wav(decoded)
        if info["trimmed_ms"]:
            meta = {"vad_applied": True, "trimmed_ms": int(info["trimmed_ms"])}
            return trimmed, meta
        # Still send clean 16k mono wav when we managed to decode it.
        if _is_wav(decoded) and not _is_wav(audio_bytes):
            meta = {"vad_applied": True, "trimmed_ms": 0}
            return decoded, meta
    except Exception:  # noqa: BLE001
        logger.debug("ASR audio pre-pass failed; sending original buffer", exc_info=True)
    return audio_bytes, meta


def detect_artifacts(text: str) -> list[str]:
    """Return artifact reasons for a segment (empty list = clean)."""
    reasons: list[str] = []
    stripped = text.strip()
    if not stripped:
        return reasons
    if _HALLUCINATION_RE.search(stripped):
        reasons.append("known_hallucination_artifact")
    if _LOOP_RE.search(stripped):
        reasons.append("repetition_loop")
    # Whole segment repeating itself verbatim (classic Whisper deloop case)
    halves = stripped.split("\n")
    if len(halves) > 1:
        unique = {h.strip().lower() for h in halves if h.strip()}
        if len(unique) == 1 and len(halves) >= 2:
            reasons.append("duplicated_line")
    return reasons


def build_hygiene_result(
    raw_result: dict,
) -> HygieneResult:
    """Normalise a verbose_json-style ASR response into text+segments+flags.

    Accepts providers with or without ``segments``; keeps the existing
    joined-text behaviour for clean audio while exposing per-segment
    confidence and flags for review.
    """
    segments_in = raw_result.get("segments") or []
    out_segments: list[dict] = []
    flags: list[dict] = []

    for index, seg in enumerate(segments_in):
        text = str(seg.get("text", "")).strip()
        if not text:
            continue
        confidence = classify_confidence(seg)
        artifact_reasons = detect_artifacts(text)
        entry = {
            "id": seg.get("id", index),
            "start": seg.get("start"),
            "end": seg.get("end"),
            "text": text,
            "confidence": confidence,
        }
        if seg.get("avg_logprob") is not None:
            entry["avg_logprob"] = round(float(seg["avg_logprob"]), 3)
        out_segments.append(entry)

        if "suspect" in confidence or confidence == "low_confidence":
            flags.append({"segment": entry["id"], "reason": confidence, "text": text[:160]})
        for reason in artifact_reasons:
            flags.append({"segment": entry["id"], "reason": reason, "text": text[:160]})

    if out_segments:
        text = "\n".join(s["text"] for s in out_segments)
    else:
        text = str(raw_result.get("text", ""))
        # No per-segment data: still run artifact detection on the whole text
        for reason in detect_artifacts(text):
            flags.append({"segment": None, "reason": reason, "text": text[:160]})

    return HygieneResult(text=text, segments=out_segments, flags=flags)


def deterministic_options(options: dict | None) -> dict:
    """Force deterministic decoding for note-generation LLM calls (plan ref B4).

    Sampling variance is an avoidable source of non-reproducible notes:
    the same transcript must produce the same draft so evaluation diffs and
    audit replays compare like with like. Temperature 0 plus a fixed seed do
    *not* eliminate hallucination by themselves — they make the evidence
    guardrails and verification results stable and reproducible instead of a
    fresh draw each run.
    """
    merged = dict(options or {})
    merged["temperature"] = 0.0
    merged["seed"] = 0
    return merged
